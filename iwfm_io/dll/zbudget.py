"""Standalone IWFM zone-budget file reader."""

from ctypes import c_int, c_double, c_char, byref
import numpy as np

from ._base import _DllFileReader, fortran_view
from ._errors import IWFMError
from ._validate import check_date, check_interval, check_window
from ._marshal import str_to_c, c_to_str, c_to_str_list, alloc_int, alloc_char


class IWFMZBudget(_DllFileReader):
    """Read an IWFM zone-budget HDF5 file.

    Parameters
    ----------
    hdf_file : str
        Path to the Z-Budget HDF5 file.
    dll_version : str, optional
        DLL version string, e.g. ``"2015.0.1248"``.  See
        :func:`iwfm_io.dll.load_dll` for full resolution order.
    dll_path : str, optional
        Explicit path to ``IWFM_C_x64.dll``.  Takes precedence over
        *dll_version*.
    """

    _OPEN_FN = "IW_ZBudget_OpenFile"
    _CLOSE_FN = "IW_ZBudget_CloseFile"
    #: the file the DLL currently serves (process-global in the DLL)
    _current_path = None

    # ------------------------------------------------------------------
    # Zone list generation
    # ------------------------------------------------------------------

    def generate_zone_list_from_file(self, zone_def_file):
        """Load zone definitions from an ASCII file."""
        c_len, c_name = str_to_c(zone_def_file)
        self._call("IW_ZBudget_GenerateZoneList_FromFile", c_name, c_len)
        self._n_zones = getattr(self, '_n_zones', 0) or -1  # zone list ready

    def generate_zone_list(self, zone_extent, elements, layers, zones,
                           zone_names_ids=None, zone_names=None):
        """Generate zone list from arrays.

        Parameters
        ----------
        zone_extent : int
            Zone extent ID (horizontal or vertical).
        elements, layers, zones : array-like of int
            Element indices, layer indices, and zone assignments.
        zone_names_ids : array-like of int, optional
            Zone IDs that have names.
        zone_names : list[str], optional
            Corresponding zone names.
        """
        from iwfm_io.dll.misc import ZoneExtentID
        if ZoneExtentID.Horizontal is None:
            ZoneExtentID._load(self._dll)
        valid_extents = {int(ZoneExtentID.Horizontal), int(ZoneExtentID.Vertical)}
        if not isinstance(zone_extent, (int, np.integer)) \
                or int(zone_extent) not in valid_extents:
            raise ValueError(
                f"zone_extent must be ZoneExtentID.Horizontal "
                f"({ZoneExtentID.Horizontal}) or ZoneExtentID.Vertical "
                f"({ZoneExtentID.Vertical}), got {zone_extent!r}")
        zone_extent = int(zone_extent)
        elements = np.asarray(list(elements), dtype=np.int32)
        layers = np.asarray(list(layers), dtype=np.int32)
        zones_arr = np.asarray(list(zones), dtype=np.int32)
        n_elems = len(elements)
        if n_elems == 0:
            raise ValueError("generate_zone_list: elements must not be empty")
        if len(layers) != n_elems or len(zones_arr) != n_elems:
            raise ValueError(
                "generate_zone_list: elements, layers and zones must have "
                f"the same length ({n_elems}, {len(layers)}, {len(zones_arr)})")
        if (elements < 1).any() or (layers < 1).any() or (zones_arr < 1).any():
            raise ValueError("generate_zone_list: element, layer and zone "
                             "ids must be >= 1")

        # the Fortran indexes the name arrays for every zone even when no
        # names were given (an out-of-bounds write with none): always
        # send one name per zone
        zone_ids_present = sorted(int(z) for z in np.unique(zones_arr))
        if zone_names_ids is None and zone_names is None:
            zone_names_ids = zone_ids_present
            zone_names = [f"Zone {z}" for z in zone_ids_present]
        elif zone_names_ids is None or zone_names is None:
            raise ValueError("generate_zone_list: pass zone_names_ids and "
                             "zone_names together")
        zone_names_ids = np.asarray(list(zone_names_ids), dtype=np.int32)
        zone_names = [str(n) for n in zone_names]
        if len(zone_names) != len(zone_names_ids):
            raise ValueError(
                "generate_zone_list: zone_names_ids and zone_names differ "
                f"in length ({len(zone_names_ids)} vs {len(zone_names)})")
        given = {int(z) for z in zone_names_ids}
        unnamed = [z for z in zone_ids_present if z not in given]
        if unnamed:
            zone_names_ids = np.asarray(list(zone_names_ids) + unnamed, dtype=np.int32)
            zone_names = zone_names + [f"Zone {z}" for z in unnamed]
        n_with_names = len(zone_names_ids)
        self._n_zones = len(zone_ids_present)

        # Pack zone names into a single buffer with offset array
        packed = "".join(zone_names)
        loc_array = []
        pos = 1
        for name in zone_names:
            loc_array.append(pos)
            pos += len(name)

        c_elems = (c_int * n_elems)(*elements)
        c_layers = (c_int * n_elems)(*layers)
        c_zones = (c_int * n_elems)(*zones_arr)
        c_name_ids = (c_int * max(n_with_names, 1))(*zone_names_ids)
        names_len, c_names_buf = str_to_c(packed) if packed else (c_int(0), (c_char * 1)())
        c_loc = (c_int * max(n_with_names, 1))(*(loc_array or [0]))

        self._call("IW_ZBudget_GenerateZoneList",
                   c_int(zone_extent), c_int(n_elems), c_elems, c_layers, c_zones,
                   c_int(n_with_names), c_name_ids, names_len, c_names_buf, c_loc)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_zones(self):
        """Number of zones (excluding undefined zone)."""
        return self._scalar_int("IW_ZBudget_GetNZones")

    @property
    def n_timesteps(self):
        """Number of time steps."""
        return self._scalar_int("IW_ZBudget_GetNTimeSteps")

    @property
    def n_title_lines(self):
        """Number of title lines."""
        return self._scalar_int("IW_ZBudget_GetNTitleLines")

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_zone_list(self):
        """Return array of zone IDs."""
        return self._int_array("IW_ZBudget_GetZoneList", self.n_zones)

    def get_zone_names(self):
        """Return list of zone names."""
        n = self.n_zones
        buf_len = n * 60
        buf = alloc_char(buf_len)
        loc_arr = alloc_int(n)
        self._call("IW_ZBudget_GetZoneNames", c_int(n), c_int(buf_len), buf, loc_arr)
        return c_to_str_list(buf, loc_arr, n)

    def get_time_specs(self):
        """Return dict with 'dates' list and 'interval' string."""
        n_data = self.n_timesteps
        date_buf_len = n_data * 32
        intv_buf_len = 32
        date_buf = alloc_char(date_buf_len)
        intv_buf = alloc_char(intv_buf_len)
        loc_arr = alloc_int(n_data)
        self._call("IW_ZBudget_GetTimeSpecs",
                   date_buf, c_int(date_buf_len), intv_buf, c_int(intv_buf_len),
                   c_int(n_data), loc_arr)
        dates = c_to_str_list(date_buf, loc_arr, n_data)
        interval = c_to_str(intv_buf, intv_buf_len)
        return {"dates": dates, "interval": interval}

    def get_title_lines(self, zone, fact_ar=1.0,
                        area_unit="SQ FT", volume_unit="CU FT"):
        """Return title lines for a zone."""
        n_titles = self.n_title_lines
        title_len = n_titles * 500
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        title_buf = alloc_char(title_len)
        loc_arr = alloc_int(n_titles)
        self._call("IW_ZBudget_GetTitleLines",
                   c_int(n_titles), c_int(zone), c_double(fact_ar),
                   c_au, c_vu, u_len,
                   title_buf, c_int(title_len), loc_arr)
        return c_to_str_list(title_buf, loc_arr, n_titles)

    def get_column_headers_general(self, area_unit="SQ FT",
                                   volume_unit="CU FT", max_columns=200):
        """Return general column headers (lumped inter-zone flows).

        *max_columns* only sizes the receiving buffers (the Fortran
        writes every column regardless, so a too-small buffer is an
        access violation); it is raised to a safe minimum internally.
        """
        if not isinstance(max_columns, (int, np.integer)) or max_columns < 1:
            raise ValueError(f"max_columns must be >= 1, got {max_columns!r}")
        max_columns = max(int(max_columns), 2000)
        buf_len = max_columns * 200
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        col_buf = alloc_char(buf_len)
        n_cols = c_int(0)
        loc_arr = alloc_int(max_columns)
        self._call("IW_ZBudget_GetColumnHeaders_General",
                   c_int(max_columns), c_au, c_vu, u_len, c_int(buf_len),
                   col_buf, byref(n_cols), loc_arr)
        headers = c_to_str_list(col_buf, loc_arr, n_cols.value)
        self._n_columns = len(headers)
        return headers

    def _column_count(self):
        n = getattr(self, "_n_columns", None)
        if n is None:
            self.get_column_headers_general()
            n = self._n_columns
        return n

    def _sim_window(self):
        """(first, last) output stamps, cached."""
        w = getattr(self, "_window", None)
        if w is None:
            dates = self.get_time_specs()["dates"]
            w = (dates[0], dates[-1]) if dates else None
            self._window = w
        return w

    def _check_zone_ids(self, zones):
        known = set(int(z) for z in self.get_zone_list())
        bad = [int(z) for z in zones if int(z) not in known]
        if bad:
            raise ValueError(
                f"zone(s) {bad[:5]} are not in the generated zone list "
                f"({len(known)} zones: {sorted(known)[:10]}...)")

    def get_column_headers_for_zone(self, zone, columns_list=None,
                                    area_unit="SQ FT", volume_unit="CU FT",
                                    max_columns=500):
        """Return column headers diversified for a specific zone.

        Returns
        -------
        headers : list[str]
        diversified_columns : np.ndarray
            Mapping from diversified column index to general column index.
        """
        if columns_list is None:
            columns_list = list(range(1, max_columns + 1))
        n_cols_list = len(columns_list)
        buf_len = max_columns * 200
        c_cols_list = (c_int * n_cols_list)(*columns_list)
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        col_buf = alloc_char(buf_len)
        n_cols = c_int(0)
        loc_arr = alloc_int(max_columns)
        div_cols = alloc_int(max_columns)
        self._call("IW_ZBudget_GetColumnHeaders_ForAZone",
                   c_int(zone), c_int(n_cols_list), c_cols_list, c_int(max_columns),
                   c_au, c_vu, u_len, c_int(buf_len),
                   col_buf, byref(n_cols), loc_arr, div_cols)
        nc = n_cols.value
        headers = c_to_str_list(col_buf, loc_arr, nc)
        return headers, np.array(div_cols[:nc], dtype=np.int32)

    def get_values_for_zone(self, zone, columns, begin_date, end_date,
                            interval, fact_ar=1.0, fact_vl=1.0):
        """Read Z-Budget data for a single zone.

        Parameters
        ----------
        zone : int
            Zone number.
        columns : list[int]
            1-based column indices (must include Time as column 1).
        begin_date, end_date : str
            Date-time strings.
        interval : str
            Output interval string.

        Returns
        -------
        np.ndarray
            Shape ``(n_times, n_columns)``.
        """
        if not getattr(self, "_n_zones", 0):
            raise IWFMError("no zone list generated yet -- call "
                            "generate_zone_list first", -1)
        cols = [int(c) for c in columns]
        if not cols or cols[0] != 1 or min(cols) < 1:
            raise ValueError("columns must start with 1 (the Time column) "
                             "and be >= 1")
        n_avail = self._column_count()
        if max(cols) > n_avail:
            raise ValueError(
                f"column {max(cols)} is out of range: this Z-Budget has "
                f"{n_avail} columns (1 = Time)")
        self._check_zone_ids([zone])
        if not isinstance(begin_date, str) or not isinstance(end_date, str):
            raise TypeError("begin_date/end_date must be IWFM date strings")
        check_window(begin_date, end_date, self._sim_window())
        interval = check_interval(interval)
        n_cols = len(columns)
        n_times = self.n_timesteps
        c_cols = (c_int * n_cols)(*columns)
        b_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        values = (c_double * (n_cols * n_times))()
        nt_out = c_int(0)
        self._call("IW_ZBudget_GetValues_ForAZone",
                   c_int(zone), c_int(n_cols), c_cols,
                   c_begin, c_end, b_len, c_intv, iv_len,
                   c_double(fact_ar), c_double(fact_vl), c_int(n_times),
                   values, byref(nt_out))
        arr = fortran_view(values, (n_cols, n_times))
        return arr[:, :nt_out.value].T.copy()

    def get_values_for_zones_interval(self, zones, columns_per_zone,
                                      begin_date, interval,
                                      fact_ar=1.0, fact_vl=1.0):
        """Read Z-Budget data for multiple zones for a single time interval.

        Parameters
        ----------
        zones : list[int]
            Zone numbers.
        columns_per_zone : np.ndarray
            2D array of column indices, shape ``(max_cols, n_zones)``.
            First row should be the Time column (1).
        begin_date : str
            Date-time string for the interval.
        interval : str
            Output interval.

        Returns
        -------
        np.ndarray
            Shape ``(max_cols, n_zones)``.
        """
        zones_arr = np.asarray(zones, dtype=np.int32)
        cols_arr = np.asarray(columns_per_zone, dtype=np.int32)
        if zones_arr.ndim != 1 or len(zones_arr) == 0:
            raise ValueError("zones must be a non-empty 1-D sequence")
        if cols_arr.ndim != 2 or cols_arr.shape[1] != len(zones_arr):
            raise ValueError(
                "columns_per_zone must be a 2-D array of shape "
                f"(max_cols, n_zones={len(zones_arr)}), got {cols_arr.shape}")
        if (cols_arr[0] != 1).any() or (cols_arr < 1).any():
            raise ValueError("columns_per_zone: first row must be 1 (Time) "
                             "and every column index >= 1")
        n_avail = self._column_count()
        if cols_arr.max() > n_avail:
            raise ValueError(
                f"column {int(cols_arr.max())} is out of range: this "
                f"Z-Budget has {n_avail} columns (1 = Time)")
        self._check_zone_ids(zones_arr.tolist())
        begin_date = check_date("begin_date", begin_date)
        window = self._sim_window()
        if window is not None:
            check_window(begin_date, window[1], window)
        interval = check_interval(interval)
        n_zones = len(zones_arr)
        n_cols_max = cols_arr.shape[0]

        c_zones = (c_int * n_zones)(*zones_arr)
        # Flatten column-major for Fortran
        flat_cols = cols_arr.flatten(order="F")
        c_cols = (c_int * len(flat_cols))(*flat_cols)
        b_len, c_begin = str_to_c(begin_date)
        iv_len, c_intv = str_to_c(interval)
        values = (c_double * (n_cols_max * n_zones))()

        self._call("IW_ZBudget_GetValues_ForSomeZones_ForAnInterval",
                   c_int(n_zones), c_zones, c_int(n_cols_max), c_cols,
                   c_begin, b_len, c_intv, iv_len,
                   c_double(fact_ar), c_double(fact_vl), values)
        return fortran_view(values, (n_cols_max, n_zones)).copy()
