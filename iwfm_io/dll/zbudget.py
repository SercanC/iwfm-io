"""Standalone IWFM zone-budget file reader."""

from ctypes import c_int, c_double, c_char, byref
import numpy as np

from ._dll import load_dll
from ._errors import _check_status
from ._marshal import str_to_c, c_to_str, c_to_str_list, alloc_int, alloc_double, alloc_char


class IWFMZBudget:
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

    def __init__(self, hdf_file, dll_version=None, dll_path=None):
        self._dll = load_dll(version=dll_version, dll_path=dll_path)
        c_len, c_name = str_to_c(hdf_file)
        iStat = c_int(0)
        self._dll.IW_ZBudget_OpenFile(c_name, c_len, byref(iStat))
        _check_status(iStat, self._dll)
        self._open = True

    def close(self):
        """Close the Z-Budget file."""
        if self._open:
            iStat = c_int(0)
            self._dll.IW_ZBudget_CloseFile(byref(iStat))
            _check_status(iStat, self._dll)
            self._open = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Zone list generation
    # ------------------------------------------------------------------

    def generate_zone_list_from_file(self, zone_def_file):
        """Load zone definitions from an ASCII file."""
        c_len, c_name = str_to_c(zone_def_file)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GenerateZoneList_FromFile(
            c_name, c_len, byref(iStat),
        )
        _check_status(iStat, self._dll)

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
        elements = np.asarray(elements, dtype=np.int32)
        layers = np.asarray(layers, dtype=np.int32)
        zones_arr = np.asarray(zones, dtype=np.int32)
        n_elems = len(elements)

        if zone_names_ids is None:
            zone_names_ids = np.array([], dtype=np.int32)
            zone_names = []
        zone_names_ids = np.asarray(zone_names_ids, dtype=np.int32)
        n_with_names = len(zone_names_ids)

        # Pack zone names into a single buffer with offset array
        packed = "".join(zone_names)
        loc_array = []
        pos = 1
        for name in zone_names:
            loc_array.append(pos)
            pos += len(name)

        c_z_extent = c_int(zone_extent)
        c_n_elems = c_int(n_elems)
        c_elems = (c_int * n_elems)(*elements)
        c_layers = (c_int * n_elems)(*layers)
        c_zones = (c_int * n_elems)(*zones_arr)
        c_n_names = c_int(n_with_names)
        c_name_ids = (c_int * max(n_with_names, 1))(*zone_names_ids)
        names_len, c_names_buf = str_to_c(packed) if packed else (c_int(0), (c_char * 1)())
        c_loc = (c_int * max(n_with_names, 1))(*(loc_array or [0]))
        iStat = c_int(0)

        self._dll.IW_ZBudget_GenerateZoneList(
            c_z_extent, c_n_elems, c_elems, c_layers, c_zones,
            c_n_names, c_name_ids, names_len, c_names_buf, c_loc,
            byref(iStat),
        )
        _check_status(iStat, self._dll)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_zones(self):
        """Number of zones (excluding undefined zone)."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetNZones(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_timesteps(self):
        """Number of time steps."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetNTimeSteps(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_title_lines(self):
        """Number of title lines."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetNTitleLines(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_zone_list(self):
        """Return array of zone IDs."""
        n = self.n_zones
        zones = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetZoneList(c_int(n), zones, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(zones, dtype=np.int32)

    def get_zone_names(self):
        """Return list of zone names."""
        n = self.n_zones
        buf_len = n * 60
        c_n = c_int(n)
        c_buf_len = c_int(buf_len)
        buf = alloc_char(buf_len)
        loc_arr = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetZoneNames(
            c_n, c_buf_len, buf, loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(buf, loc_arr, n)

    def get_time_specs(self):
        """Return dict with 'dates' list and 'interval' string."""
        n_data = self.n_timesteps
        date_buf_len = n_data * 32
        intv_buf_len = 32
        c_len_dates = c_int(date_buf_len)
        c_len_intv = c_int(intv_buf_len)
        c_n_data = c_int(n_data)
        date_buf = alloc_char(date_buf_len)
        intv_buf = alloc_char(intv_buf_len)
        loc_arr = alloc_int(n_data)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetTimeSpecs(
            date_buf, c_len_dates, intv_buf, c_len_intv,
            c_n_data, loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        dates = c_to_str_list(date_buf, loc_arr, n_data)
        interval = c_to_str(intv_buf, intv_buf_len)
        return {"dates": dates, "interval": interval}

    def get_title_lines(self, zone, fact_ar=1.0,
                        area_unit="SQ FT", volume_unit="CU FT"):
        """Return title lines for a zone."""
        n_titles = self.n_title_lines
        title_len = n_titles * 500
        c_n_titles = c_int(n_titles)
        c_zone = c_int(zone)
        c_fact = c_double(fact_ar)
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        c_total = c_int(title_len)
        title_buf = alloc_char(title_len)
        loc_arr = alloc_int(n_titles)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetTitleLines(
            c_n_titles, c_zone, c_fact,
            c_au, c_vu, u_len,
            title_buf, c_total, loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(title_buf, loc_arr, n_titles)

    def get_column_headers_general(self, area_unit="SQ FT",
                                   volume_unit="CU FT", max_columns=200):
        """Return general column headers (lumped inter-zone flows)."""
        buf_len = max_columns * 200
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        c_max = c_int(max_columns)
        c_buf_len = c_int(buf_len)
        col_buf = alloc_char(buf_len)
        n_cols = c_int(0)
        loc_arr = alloc_int(max_columns)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetColumnHeaders_General(
            c_max, c_au, c_vu, u_len, c_buf_len,
            col_buf, byref(n_cols), loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(col_buf, loc_arr, n_cols.value)

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
        c_zone = c_int(zone)
        c_n_cols_list = c_int(n_cols_list)
        c_cols_list = (c_int * n_cols_list)(*columns_list)
        c_max = c_int(max_columns)
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        c_buf_len = c_int(buf_len)
        col_buf = alloc_char(buf_len)
        n_cols = c_int(0)
        loc_arr = alloc_int(max_columns)
        div_cols = alloc_int(max_columns)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetColumnHeaders_ForAZone(
            c_zone, c_n_cols_list, c_cols_list, c_max,
            c_au, c_vu, u_len, c_buf_len,
            col_buf, byref(n_cols), loc_arr, div_cols, byref(iStat),
        )
        _check_status(iStat, self._dll)
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
        n_cols = len(columns)
        n_times = self.n_timesteps
        c_zone = c_int(zone)
        c_n_cols = c_int(n_cols)
        c_cols = (c_int * n_cols)(*columns)
        b_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        c_far = c_double(fact_ar)
        c_fvl = c_double(fact_vl)
        c_nt = c_int(n_times)
        values = (c_double * (n_cols * n_times))()
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_ZBudget_GetValues_ForAZone(
            c_zone, c_n_cols, c_cols,
            c_begin, c_end, b_len, c_intv, iv_len,
            c_far, c_fvl, c_nt, values, byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        arr = np.frombuffer(values, dtype=np.float64).reshape(
            (n_cols, n_times), order="F"
        )
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
        n_zones = len(zones_arr)
        n_cols_max = cols_arr.shape[0]

        c_n_zones = c_int(n_zones)
        c_zones = (c_int * n_zones)(*zones_arr)
        c_n_cols_max = c_int(n_cols_max)
        # Flatten column-major for Fortran
        flat_cols = cols_arr.flatten(order="F")
        c_cols = (c_int * len(flat_cols))(*flat_cols)
        b_len, c_begin = str_to_c(begin_date)
        iv_len, c_intv = str_to_c(interval)
        c_far = c_double(fact_ar)
        c_fvl = c_double(fact_vl)
        values = (c_double * (n_cols_max * n_zones))()
        iStat = c_int(0)

        self._dll.IW_ZBudget_GetValues_ForSomeZones_ForAnInterval(
            c_n_zones, c_zones, c_n_cols_max, c_cols,
            c_begin, b_len, c_intv, iv_len,
            c_far, c_fvl, values, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.frombuffer(values, dtype=np.float64).reshape(
            (n_cols_max, n_zones), order="F"
        ).copy()
