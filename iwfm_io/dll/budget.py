"""Standalone IWFM budget file reader."""

from ctypes import c_int, c_double, c_char, byref
import numpy as np

from ._dll import load_dll
from ._errors import _check_status
from ._marshal import str_to_c, c_to_str, c_to_str_list, alloc_int, alloc_double, alloc_char


class IWFMBudget:
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

    def __init__(self, hdf_file, dll_version=None, dll_path=None):
        self._dll = load_dll(version=dll_version, dll_path=dll_path)
        c_len, c_name = str_to_c(hdf_file)
        iStat = c_int(0)
        self._dll.IW_Budget_OpenFile(c_name, c_len, byref(iStat))
        _check_status(iStat, self._dll)
        self._open = True

    def close(self):
        """Close the budget file."""
        if self._open:
            iStat = c_int(0)
            self._dll.IW_Budget_CloseFile(byref(iStat))
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
    # Properties
    # ------------------------------------------------------------------

    @property
    def n_locations(self):
        """Number of budget locations."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_GetNLocations(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_timesteps(self):
        """Number of time steps in the budget file."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_GetNTimeSteps(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_title_lines(self):
        """Number of persistent title lines."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_GetNTitleLines(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def title_length(self):
        """Maximum title line length."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_GetTitleLength(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    # ------------------------------------------------------------------
    # Methods
    # ------------------------------------------------------------------

    def get_location_names(self):
        """Return a list of budget location names."""
        n_loc = self.n_locations
        buf_len = n_loc * 100
        c_buf_len = c_int(buf_len)
        c_n_loc = c_int(n_loc)
        buf = alloc_char(buf_len)
        loc_arr = alloc_int(n_loc)
        iStat = c_int(0)
        self._dll.IW_Budget_GetLocationNames(
            buf, c_buf_len, c_n_loc, loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(buf, loc_arr, n_loc)

    def get_time_specs(self):
        """Return dict with 'dates' list, 'interval' string."""
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
        self._dll.IW_Budget_GetTimeSpecs(
            date_buf, c_len_dates, intv_buf, c_len_intv,
            c_n_data, loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        dates = c_to_str_list(date_buf, loc_arr, n_data)
        interval = c_to_str(intv_buf, intv_buf_len)
        return {"dates": dates, "interval": interval}

    def get_title_lines(self, location, fact_area=1.0,
                        length_unit="FT", area_unit="SQ FT",
                        volume_unit="CU FT", alt_loc_name=""):
        """Return title lines for a location."""
        n_titles = self.n_title_lines
        title_len = self.title_length
        total_len = n_titles * title_len
        c_n_titles = c_int(n_titles)
        c_loc = c_int(location)
        c_fact = c_double(fact_area)
        unit_len, c_lu = str_to_c(length_unit)
        _, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        alt_len, c_alt = str_to_c(alt_loc_name)
        c_total = c_int(total_len)
        title_buf = alloc_char(total_len)
        loc_arr = alloc_int(n_titles)
        iStat = c_int(0)
        self._dll.IW_Budget_GetTitleLines(
            c_n_titles, c_loc, c_fact,
            c_lu, c_au, c_vu, unit_len,
            c_alt, alt_len,
            title_buf, c_total, loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(title_buf, loc_arr, n_titles)

    def get_n_columns(self, location):
        """Return the number of data columns for a location."""
        c_loc = c_int(location)
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_GetNColumns(c_loc, byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_column_headers(self, location, length_unit="FT",
                           area_unit="SQ FT", volume_unit="CU FT"):
        """Return column header strings for a location."""
        n_cols = self.get_n_columns(location)
        buf_len = n_cols * 200
        c_loc = c_int(location)
        c_buf_len = c_int(buf_len)
        c_n_cols = c_int(n_cols)
        unit_len, c_lu = str_to_c(length_unit)
        _, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        col_buf = alloc_char(buf_len)
        loc_arr = alloc_int(n_cols)
        iStat = c_int(0)
        self._dll.IW_Budget_GetColumnHeaders(
            c_loc, col_buf, c_buf_len, c_n_cols,
            c_lu, c_au, c_vu, unit_len,
            loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
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
        n_cols = len(columns)
        n_times = self.n_timesteps
        c_loc = c_int(location)
        c_n_cols = c_int(n_cols)
        cols_arr = (c_int * n_cols)(*columns)
        b_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        c_flt = c_double(fact_lt)
        c_far = c_double(fact_ar)
        c_fvl = c_double(fact_vl)
        c_nt = c_int(n_times)
        # Values shape: (n_cols+1, n_times) in Fortran order
        values = (c_double * ((n_cols + 1) * n_times))()
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_GetValues(
            c_loc, c_n_cols, cols_arr,
            c_begin, c_end, b_len, c_intv, iv_len,
            c_flt, c_far, c_fvl,
            c_nt, values, byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        arr = np.frombuffer(values, dtype=np.float64).reshape(
            (n_cols + 1, n_times), order="F"
        )
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
        n_times = self.n_timesteps
        c_loc = c_int(location)
        c_col = c_int(column)
        iv_len, c_intv = str_to_c(interval)
        b_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        c_flt = c_double(fact_lt)
        c_far = c_double(fact_ar)
        c_fvl = c_double(fact_vl)
        c_dim_in = c_int(n_times)
        dim_out = c_int(0)
        dates = alloc_double(n_times)
        vals = alloc_double(n_times)
        iStat = c_int(0)
        self._dll.IW_Budget_GetValues_ForAColumn(
            c_loc, c_col, c_intv, iv_len,
            c_begin, c_end, b_len,
            c_flt, c_far, c_fvl,
            c_dim_in, byref(dim_out), dates, vals, byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = dim_out.value
        return np.array(dates[:n], dtype=np.float64), np.array(vals[:n], dtype=np.float64)

    def are_n_columns_same(self):
        """Return True if all locations have the same number of columns."""
        result = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Budget_AreNColumnsSame(byref(result), byref(iStat))
        _check_status(iStat, self._dll)
        return result.value == 1
