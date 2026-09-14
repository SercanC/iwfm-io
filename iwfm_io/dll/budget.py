"""Standalone IWFM budget file reader."""

from ctypes import c_int, c_double, byref
import numpy as np

from ._base import _DllFileReader, fortran_view
from ._validate import check_ids, check_interval, check_range, check_window
from ._marshal import str_to_c, c_to_str, c_to_str_list, alloc_int, alloc_double, alloc_char


class IWFMBudget(_DllFileReader):
    """Read an IWFM budget HDF5/binary file.

    Parameters
    ----------
    hdf_file : str
        Path to the budget output file.
    dll_version : str, optional
        DLL version string, e.g. ``"2015.0.1248"``.  See
        :func:`iwfm_io.dll.load_dll` for full resolution order.
    dll_path : str, optional
        Explicit path to ``IWFM_C_x64.dll``.  Takes precedence over
        *dll_version*.
    """

    _OPEN_FN = "IW_Budget_OpenFile"
    _CLOSE_FN = "IW_Budget_CloseFile"
    #: the file the DLL currently serves (process-global in the DLL)
    _current_path = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_locations(self):
        """Number of budget locations."""
        return self._scalar_int("IW_Budget_GetNLocations")

    @property
    def n_timesteps(self):
        """Number of time steps in the budget file."""
        return self._scalar_int("IW_Budget_GetNTimeSteps")

    @property
    def n_title_lines(self):
        """Number of persistent title lines."""
        return self._scalar_int("IW_Budget_GetNTitleLines")

    @property
    def title_length(self):
        """Maximum title line length."""
        return self._scalar_int("IW_Budget_GetTitleLength")

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_location_names(self):
        """Return a list of budget location names."""
        n_loc = self.n_locations
        buf_len = n_loc * 100
        buf = alloc_char(buf_len)
        loc_arr = alloc_int(n_loc)
        self._call("IW_Budget_GetLocationNames",
                   buf, c_int(buf_len), c_int(n_loc), loc_arr)
        return c_to_str_list(buf, loc_arr, n_loc)

    def get_time_specs(self):
        """Return dict with 'dates' list, 'interval' string."""
        n_data = self.n_timesteps
        date_buf_len = n_data * 32
        intv_buf_len = 32
        date_buf = alloc_char(date_buf_len)
        intv_buf = alloc_char(intv_buf_len)
        loc_arr = alloc_int(n_data)
        self._call("IW_Budget_GetTimeSpecs",
                   date_buf, c_int(date_buf_len), intv_buf, c_int(intv_buf_len),
                   c_int(n_data), loc_arr)
        dates = c_to_str_list(date_buf, loc_arr, n_data)
        interval = c_to_str(intv_buf, intv_buf_len)
        return {"dates": dates, "interval": interval}

    def get_title_lines(self, location, fact_area=1.0,
                        length_unit="FT", area_unit="SQ FT",
                        volume_unit="CU FT", alt_loc_name=""):
        """Return title lines for a location."""
        location = check_range("location", location, self.n_locations)
        n_titles = self.n_title_lines
        title_len = self.title_length
        total_len = n_titles * title_len
        unit_len, c_lu = str_to_c(length_unit)
        _, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        alt_len, c_alt = str_to_c(alt_loc_name)
        title_buf = alloc_char(total_len)
        loc_arr = alloc_int(n_titles)
        self._call("IW_Budget_GetTitleLines",
                   c_int(n_titles), c_int(location), c_double(fact_area),
                   c_lu, c_au, c_vu, unit_len,
                   c_alt, alt_len,
                   title_buf, c_int(total_len), loc_arr)
        return c_to_str_list(title_buf, loc_arr, n_titles)

    def get_n_columns(self, location):
        """Return the number of data columns for a location."""
        location = check_range("location", location, self.n_locations)
        return self._scalar_int("IW_Budget_GetNColumns", c_int(location))

    def get_column_headers(self, location, length_unit="FT",
                           area_unit="SQ FT", volume_unit="CU FT"):
        """Return column header strings for a location."""
        location = check_range("location", location, self.n_locations)
        n_cols = self.get_n_columns(location)
        buf_len = n_cols * 200
        unit_len, c_lu = str_to_c(length_unit)
        _, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        col_buf = alloc_char(buf_len)
        loc_arr = alloc_int(n_cols)
        self._call("IW_Budget_GetColumnHeaders",
                   c_int(location), col_buf, c_int(buf_len), c_int(n_cols),
                   c_lu, c_au, c_vu, unit_len,
                   loc_arr)
        return c_to_str_list(col_buf, loc_arr, n_cols)

    def get_values(self, location, columns, begin_date, end_date,
                   interval, fact_lt=1.0, fact_ar=1.0, fact_vl=1.0):
        """Read budget values for selected columns at a location.

        Parameters
        ----------
        location : int
            1-based location index.
        columns : list[int]
            1-based column indices to read.
        begin_date, end_date : str
            Date-time strings.
        interval : str
            Output interval (e.g. ``"1MON"``).

        Returns
        -------
        np.ndarray
            Shape ``(n_times, n_columns+1)`` — first column is time.
        """
        location = check_range("location", location, self.n_locations)
        n_cols = int(self.get_n_columns(location))
        columns = list(check_ids("columns", columns, n_cols))
        check_window(begin_date, end_date)
        interval = check_interval(interval)
        n_cols = len(columns)
        n_times = self.n_timesteps
        cols_arr = (c_int * n_cols)(*columns)
        b_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        # Values shape: (n_cols+1, n_times) in Fortran order
        values = (c_double * ((n_cols + 1) * n_times))()
        nt_out = c_int(0)
        self._call("IW_Budget_GetValues",
                   c_int(location), c_int(n_cols), cols_arr,
                   c_begin, c_end, b_len, c_intv, iv_len,
                   c_double(fact_lt), c_double(fact_ar), c_double(fact_vl),
                   c_int(n_times), values, byref(nt_out))
        arr = fortran_view(values, (n_cols + 1, n_times))
        return arr[:, :nt_out.value].T.copy()

    def get_values_for_column(self, location, column, interval,
                              begin_date, end_date,
                              fact_lt=1.0, fact_ar=1.0, fact_vl=1.0):
        """Read a single column from an HDF budget file.

        Returns
        -------
        dates : np.ndarray
        values : np.ndarray
        """
        location = check_range("location", location, self.n_locations)
        n_times = self.n_timesteps
        iv_len, c_intv = str_to_c(interval)
        b_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        dim_out = c_int(0)
        dates = alloc_double(n_times)
        vals = alloc_double(n_times)
        self._call("IW_Budget_GetValues_ForAColumn",
                   c_int(location), c_int(column), c_intv, iv_len,
                   c_begin, c_end, b_len,
                   c_double(fact_lt), c_double(fact_ar), c_double(fact_vl),
                   c_int(n_times), byref(dim_out), dates, vals)
        n = dim_out.value
        return np.array(dates[:n], dtype=np.float64), np.array(vals[:n], dtype=np.float64)

    def are_n_columns_same(self):
        """Return True if all locations have the same number of columns."""
        return self._scalar_int("IW_Budget_AreNColumnsSame") == 1
