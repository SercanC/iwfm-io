"""IWFM Model wrapper."""

from ctypes import c_int, c_double, c_char, byref
import numpy as np
import pandas as pd

try:
    import geopandas as gpd
    from shapely.geometry import Point, Polygon
    _HAS_GEO = True
except ImportError:
    _HAS_GEO = False

from ._dll import load_dll
from ._errors import IWFMError, _check_status
from ._marshal import str_to_c, c_to_str, c_to_str_list, alloc_int, alloc_double, alloc_char


class IWFMModel:
    """Python wrapper around the IWFM simulation model DLL.

    Parameters
    ----------
    preprocessor_file : str
        Path to the Preprocessor Main Input file (e.g. ``PreProcessor_MAIN.IN``).
    simulation_file : str, optional
        Path to the simulation main input file.
    wsa_file : str, optional
        Path to the WSA file (Water Supply Adjustment).
    is_routed_streams : bool
        Whether streams are routed (default True).
    is_for_inquiry : bool
        Open in inquiry-only mode (default False).
    dll_version : str, optional
        DLL version string, e.g. ``"2015.0.1248"``.  Resolved via
        ``dlls/{version}/``, ``IWFM_DLL_VERSION`` env var, and
        ``dlls/default_version.txt`` in that order.  See
        :func:`iwfm_io.dll.load_dll` for full resolution order.
    dll_path : str, optional
        Explicit path to ``IWFM_C_x64.dll``.  Takes precedence over
        *dll_version*.
    """

    def __init__(self, preprocessor_file, simulation_file="",
                 wsa_file="", is_routed_streams=True,
                 is_for_inquiry=False, dll_version=None, dll_path=None):
        self._dll = load_dll(version=dll_version, dll_path=dll_path)
        self._model_id = None
        self._open = False
        self._cache = {}
        self._is_for_inquiry = bool(is_for_inquiry)

        pp_len, c_pp = str_to_c(preprocessor_file)
        sim_len, c_sim = str_to_c(simulation_file)
        c_routed = c_int(1 if is_routed_streams else 0)
        c_inquiry = c_int(1 if is_for_inquiry else 0)
        model_id = c_int(0)
        iStat = c_int(0)

        if wsa_file:
            wsa_len, c_wsa = str_to_c(wsa_file)
            self._dll.IW_Model_WSA_New(
                pp_len, c_pp, sim_len, c_sim, wsa_len, c_wsa,
                c_routed, c_inquiry, byref(model_id), byref(iStat),
            )
        else:
            self._dll.IW_Model_New(
                pp_len, c_pp, sim_len, c_sim,
                c_routed, c_inquiry, byref(model_id), byref(iStat),
            )
        _check_status(iStat, self._dll)
        self._model_id = model_id.value
        self._open = True

    def close(self):
        """Kill the model and free resources."""
        if self._open:
            iStat = c_int(0)
            self._dll.IW_Model_Kill(byref(iStat))
            _check_status(iStat, self._dll)
            self._open = False
            self._cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @classmethod
    def switch_to(cls, dll, model_id):
        """Switch the active model (when multiple are loaded)."""
        iStat = c_int(0)
        dll.IW_Model_Switch(c_int(model_id), byref(iStat))
        _check_status(iStat, dll)

    # ==================================================================
    # Simulation control
    # ==================================================================

    def simulate(self):
        """Run the entire simulation."""
        iStat = c_int(0)
        self._dll.IW_Model_SimulateAll(byref(iStat))
        _check_status(iStat, self._dll)

    def simulate_timestep(self):
        """Advance one time step."""
        iStat = c_int(0)
        self._dll.IW_Model_SimulateForOneTimeStep(byref(iStat))
        _check_status(iStat, self._dll)

    def simulate_interval(self, interval):
        """Simulate for a specified interval (e.g. '1MON')."""
        iv_len, c_iv = str_to_c(interval)
        iStat = c_int(0)
        self._dll.IW_Model_SimulateForAnInterval(iv_len, c_iv, byref(iStat))
        _check_status(iStat, self._dll)

    def advance_time(self):
        """Advance the simulation clock by one time step."""
        iStat = c_int(0)
        self._dll.IW_Model_AdvanceTime(byref(iStat))
        _check_status(iStat, self._dll)

    def read_timeseries_data(self):
        """Read time-series input data for the current time step."""
        iStat = c_int(0)
        self._dll.IW_Model_ReadTSData(byref(iStat))
        _check_status(iStat, self._dll)

    def read_timeseries_data_overwrite(self, region_lu_areas, diversions_idx,
                                       diversions_val, inflows_idx, inflows_val,
                                       bypasses_idx, bypasses_val):
        """Read time-series data with user-supplied overrides."""
        region_lu = np.asarray(region_lu_areas, dtype=np.float64)
        n_sub, n_lu = region_lu.shape
        n_div = len(diversions_idx)
        n_inf = len(inflows_idx)
        n_byp = len(bypasses_idx)

        c_rlu = (c_double * region_lu.size)(*region_lu.flatten(order="F"))
        c_div_idx = (c_int * n_div)(*diversions_idx)
        c_div_val = (c_double * n_div)(*diversions_val)
        c_inf_idx = (c_int * n_inf)(*inflows_idx)
        c_inf_val = (c_double * n_inf)(*inflows_val)
        c_byp_idx = (c_int * n_byp)(*bypasses_idx)
        c_byp_val = (c_double * n_byp)(*bypasses_val)
        iStat = c_int(0)

        self._dll.IW_Model_ReadTSData_Overwrite(
            c_int(n_lu), c_int(n_sub), c_rlu,
            c_int(n_div), c_div_idx, c_div_val,
            c_int(n_inf), c_inf_idx, c_inf_val,
            c_int(n_byp), c_byp_idx, c_byp_val,
            byref(iStat),
        )
        _check_status(iStat, self._dll)

    def print_results(self):
        """Write simulation results for the current time step."""
        iStat = c_int(0)
        self._dll.IW_Model_PrintResults(byref(iStat))
        _check_status(iStat, self._dll)

    def advance_state(self):
        """Advance the model state in time."""
        iStat = c_int(0)
        self._dll.IW_Model_AdvanceState(byref(iStat))
        _check_status(iStat, self._dll)

    def turn_supply_adjustment(self, diversion=True, pumping=True):
        """Turn supply adjustment on/off."""
        iStat = c_int(0)
        self._dll.IW_Model_TurnSupplyAdjustOnOff(
            c_int(1 if diversion else 0),
            c_int(1 if pumping else 0),
            byref(iStat),
        )
        _check_status(iStat, self._dll)

    def restore_pumping_to_read_values(self):
        """Restore pumping to file-specified values."""
        iStat = c_int(0)
        self._dll.IW_Model_RestorePumpingToReadValues(byref(iStat))
        _check_status(iStat, self._dll)

    def set_supply_adjustment_max_iters(self, n):
        """Set maximum iterations for supply adjustment."""
        iStat = c_int(0)
        self._dll.IW_Model_SetSupplyAdjustmentMaxIters(c_int(n), byref(iStat))
        _check_status(iStat, self._dll)

    def set_supply_adjustment_tolerance(self, tol):
        """Set convergence tolerance for supply adjustment."""
        iStat = c_int(0)
        self._dll.IW_Model_SetSupplyAdjustmentTolerance(c_double(tol), byref(iStat))
        _check_status(iStat, self._dll)

    def compute_future_water_demands(self, end_date):
        """Compute future water demands up to end_date."""
        d_len, c_date = str_to_c(end_date)
        iStat = c_int(0)
        self._dll.IW_Model_ComputeFutureWaterDemands(d_len, c_date, byref(iStat))
        _check_status(iStat, self._dll)

    @staticmethod
    def delete_inquiry_data_file(dll, sim_filename):
        """Delete the inquiry data file for a simulation."""
        s_len, c_sim = str_to_c(sim_filename)
        iStat = c_int(0)
        dll.IW_Model_DeleteInquiryDataFile(s_len, c_sim, byref(iStat))
        _check_status(iStat, dll)

    # ==================================================================
    # Time queries
    # ==================================================================

    @property
    def current_date_time(self):
        """Current simulation date-time string."""
        buf_len = 32
        c_len = c_int(buf_len)
        buf = alloc_char(buf_len)
        iStat = c_int(0)
        self._dll.IW_Model_GetCurrentDateAndTime(c_len, buf, byref(iStat))
        _check_status(iStat, self._dll)
        return c_to_str(buf, buf_len)

    @property
    def n_timesteps(self):
        """Total number of simulation time steps."""
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNTimeSteps(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def is_end_of_simulation(self):
        """True if simulation has reached its end."""
        val = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_IsEndOfSimulation(byref(val), byref(iStat))
        _check_status(iStat, self._dll)
        return val.value != 0

    def get_time_specs(self):
        """Return dict with 'dates', 'interval'."""
        n_data = self.n_timesteps
        date_buf_len = n_data * 32
        intv_buf_len = 32
        date_buf = alloc_char(date_buf_len)
        intv_buf = alloc_char(intv_buf_len)
        loc_arr = alloc_int(n_data)
        iStat = c_int(0)
        self._dll.IW_Model_GetTimeSpecs(
            date_buf, c_int(date_buf_len), intv_buf, c_int(intv_buf_len),
            c_int(n_data), loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        dates = c_to_str_list(date_buf, loc_arr, n_data)
        interval = c_to_str(intv_buf, intv_buf_len)
        return {"dates": dates, "interval": interval}

    def get_output_intervals(self):
        """Return list of available output interval strings."""
        buf_len = 1024
        max_intervals = 20
        buf = alloc_char(buf_len)
        loc_arr = alloc_int(max_intervals)
        n_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetOutputIntervals(
            buf, c_int(buf_len), loc_arr, c_int(max_intervals),
            byref(n_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(buf, loc_arr, n_out.value)

    # ==================================================================
    # Model overview
    # ==================================================================

    def describe(self):
        """Return a JSON-serializable summary of the model.

        One call that answers "what is this model and what data can I ask
        it for?" — useful to orient yourself (``print(json.dumps(d,
        indent=2))``) or for an AI agent deciding what to query next.
        Sections the DLL cannot provide (e.g. in inquiry mode on a
        partially instantiated model) are reported as None instead of
        raising.

        Returns
        -------
        dict
            Keys: ``source``, ``grid``, ``streams``, ``lakes``,
            ``simulation``, ``budgets``.
        """

        def _try(fn):
            try:
                return fn()
            except Exception:
                return None

        info = {"source": "IWFM DLL"}
        info["grid"] = _try(lambda: {
            "n_nodes": int(self.n_nodes),
            "n_elements": int(self.n_elements),
            "n_layers": int(self.n_layers),
            "n_subregions": int(self.n_subregions),
            "subregion_names": {
                int(i): self.get_subregion_name(int(i))
                for i in self.get_subregion_ids()
            },
        })
        info["streams"] = _try(lambda: {
            "n_reaches": int(self.n_reaches),
            "n_stream_nodes": int(self.n_stream_nodes),
            "n_diversions": int(self.n_diversions),
        })
        info["lakes"] = _try(lambda: {"n_lakes": int(self.n_lakes)})

        def _sim_info():
            ts = self.get_time_specs()
            dates = ts["dates"]
            return {
                "begins": dates[0] if dates else None,
                "ends": dates[-1] if dates else None,
                "timestep": ts["interval"],
                "n_timesteps": int(self.n_timesteps),
            }

        info["simulation"] = _try(_sim_info)
        info["budgets"] = _try(
            lambda: [b["name"] for b in self.get_budget_list()])
        return info

    def __repr__(self):
        if not self._open:
            return "<IWFMModel: closed>"
        try:
            return (f"<IWFMModel: {self.n_nodes} nodes, "
                    f"{self.n_elements} elements, {self.n_layers} layers>")
        except Exception:
            return "<IWFMModel>"

    # ==================================================================
    # Grid geometry
    # ==================================================================

    @property
    def n_nodes(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNNodes(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_elements(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNElements(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_layers(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNLayers(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_subregions(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNSubregions(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_node_ids(self):
        n = self.n_nodes
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetNodeIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_node_coordinates(self):
        """Return (x, y) arrays of node coordinates."""
        n = self.n_nodes
        x = alloc_double(n)
        y = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetNodeXY(c_int(n), x, y, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(x, dtype=np.float64), np.array(y, dtype=np.float64)

    def get_element_ids(self):
        n = self.n_elements
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetElementIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_element_config(self, element):
        """Return vertex node indices for an element (4 values; 0 = triangle)."""
        nodes = alloc_int(4)
        iStat = c_int(0)
        self._dll.IW_Model_GetElementConfigData(
            c_int(element), c_int(4), nodes, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_subregion_ids(self):
        n = self.n_subregions
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetSubregionIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_subregion_name(self, subregion):
        buf_len = 100
        buf = alloc_char(buf_len)
        iStat = c_int(0)
        self._dll.IW_Model_GetSubregionName(
            c_int(subregion), c_int(buf_len), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str(buf, buf_len)

    def get_element_subregions(self):
        n = self.n_elements
        subs = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetElemSubregions(c_int(n), subs, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(subs, dtype=np.int32)

    # ==================================================================
    # Stratigraphy & aquifer parameters
    # ==================================================================

    def get_ground_surface_elevation(self):
        n = self.n_nodes
        elev = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetGSElev(c_int(n), elev, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(elev, dtype=np.float64)

    def get_aquifer_top_elevation(self):
        """Shape (n_nodes, n_layers)."""
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferTopElev(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquifer_bottom_elevation(self):
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferBottomElev(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquifer_horizontal_k(self):
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferHorizontalK(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquifer_vertical_k(self):
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferVerticalK(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquitard_vertical_k(self):
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquitardVerticalK(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquifer_specific_yield(self):
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferSy(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquifer_specific_storage(self):
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferSs(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_aquifer_parameters(self):
        """Return all aquifer parameters as a dict of arrays."""
        nn, nl = self.n_nodes, self.n_layers
        sz = nn * nl
        kh = alloc_double(sz)
        akv = alloc_double(sz)
        aqkv = alloc_double(sz)
        sy = alloc_double(sz)
        ss = alloc_double(sz)
        iStat = c_int(0)
        self._dll.IW_Model_GetAquiferParameters(
            c_int(nn), c_int(nl), kh, akv, aqkv, sy, ss, byref(iStat),
        )
        _check_status(iStat, self._dll)
        shape = (nn, nl)
        return {
            "Kh": np.frombuffer(kh, dtype=np.float64).reshape(shape, order="F").copy(),
            "AquiferKv": np.frombuffer(akv, dtype=np.float64).reshape(shape, order="F").copy(),
            "AquitardKv": np.frombuffer(aqkv, dtype=np.float64).reshape(shape, order="F").copy(),
            "Sy": np.frombuffer(sy, dtype=np.float64).reshape(shape, order="F").copy(),
            "Ss": np.frombuffer(ss, dtype=np.float64).reshape(shape, order="F").copy(),
        }

    def get_stratigraphy_at_xy(self, x, y):
        """Return stratigraphy at a coordinate."""
        nl = self.n_layers
        gs = c_double(0.0)
        tops = alloc_double(nl)
        bots = alloc_double(nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetStratigraphy_AtXYCoordinate(
            c_int(nl), c_double(x), c_double(y),
            byref(gs), tops, bots, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return {
            "GSElev": gs.value,
            "TopElevs": np.array(tops, dtype=np.float64),
            "BottomElevs": np.array(bots, dtype=np.float64),
        }

    # ==================================================================
    # Parametric grids
    # ==================================================================

    def get_n_parametric_grids(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWNParametricGrids(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_n_parametric_nodes(self, grid_id):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWNParametricNodes(c_int(grid_id), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_n_parametric_elements(self, grid_id):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWNParametricElements(c_int(grid_id), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_parametric_node_xy(self, grid_id):
        n = self.get_n_parametric_nodes(grid_id)
        x = alloc_double(n)
        y = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWParametricNodeXY(
            c_int(grid_id), c_int(n), x, y, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(x, dtype=np.float64), np.array(y, dtype=np.float64)

    def get_parametric_element_config(self, grid_id, elem_id):
        verts = alloc_int(4)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWParametricElementConfigData(
            c_int(grid_id), c_int(elem_id), verts, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(verts, dtype=np.int32)

    def get_parametric_aquifer_parameters(self, grid_id):
        n = self.get_n_parametric_nodes(grid_id)
        nl = self.n_layers
        sz = n * nl
        kh = alloc_double(sz)
        akv = alloc_double(sz)
        aqkv = alloc_double(sz)
        sy = alloc_double(sz)
        ss = alloc_double(sz)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWParametricAquiferParameters(
            c_int(grid_id), c_int(n), c_int(nl),
            kh, akv, aqkv, sy, ss, byref(iStat),
        )
        _check_status(iStat, self._dll)
        shape = (n, nl)
        return {
            "Kh": np.frombuffer(kh, dtype=np.float64).reshape(shape, order="F").copy(),
            "AquiferKv": np.frombuffer(akv, dtype=np.float64).reshape(shape, order="F").copy(),
            "AquitardKv": np.frombuffer(aqkv, dtype=np.float64).reshape(shape, order="F").copy(),
            "Sy": np.frombuffer(sy, dtype=np.float64).reshape(shape, order="F").copy(),
            "Ss": np.frombuffer(ss, dtype=np.float64).reshape(shape, order="F").copy(),
        }

    # ==================================================================
    # Groundwater results
    # ==================================================================

    def get_gw_heads_initial(self):
        """Shape (n_nodes, n_layers)."""
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWHeadsIC(c_int(nn), c_int(nl), buf, byref(iStat))
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_gw_heads_for_layer(self, layer, begin_date, end_date, factor=1.0):
        """Return (dates, heads) for a layer over a date range.

        dates: 1D array, heads: shape (n_nodes, n_times).
        """
        nn = self.n_nodes
        nt = self.n_timesteps
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        dates = alloc_double(nt)
        heads = alloc_double(nn * nt)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWHeads_ForALayer(
            c_int(layer), c_begin, c_end, d_len, c_double(factor),
            c_int(nn), c_int(nt), dates, heads, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return (
            np.array(dates, dtype=np.float64),
            np.frombuffer(heads, dtype=np.float64).reshape((nn, nt), order="F").copy(),
        )

    def get_gw_heads_all(self, previous=False, factor=1.0):
        """Current timestep heads, shape (n_nodes, n_layers)."""
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetGWHeads_All(
            c_int(nn), c_int(nl), c_int(1 if previous else 0),
            c_double(factor), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    def get_subsidence_all(self, factor=1.0):
        """Current timestep subsidence, shape (n_nodes, n_layers)."""
        nn, nl = self.n_nodes, self.n_layers
        buf = alloc_double(nn * nl)
        iStat = c_int(0)
        self._dll.IW_Model_GetSubsidence_All(
            c_int(nn), c_int(nl), c_double(factor), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape((nn, nl), order="F").copy()

    # ==================================================================
    # Stream network structure
    # ==================================================================

    @property
    def n_stream_nodes(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNStrmNodes(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_reaches(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNReaches(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_stream_node_ids(self):
        n = self.n_stream_nodes
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmNodeIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_reach_ids(self):
        n = self.n_reaches
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_reaches_for_stream_nodes(self, node_indices):
        n = len(node_indices)
        nodes = (c_int * n)(*node_indices)
        reaches = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReaches_ForStrmNodes(
            c_int(n), nodes, reaches, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(reaches, dtype=np.int32)

    def get_reach_upstream_nodes(self):
        n = self.n_reaches
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachUpstrmNodes(c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_reach_downstream_nodes(self):
        n = self.n_reaches
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachDownstrmNodes(c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_reach_outflow_destinations(self):
        n = self.n_reaches
        dest = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachOutflowDest(c_int(n), dest, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(dest, dtype=np.int32)

    def get_reach_outflow_dest_types(self):
        n = self.n_reaches
        dt = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachOutflowDestTypes(c_int(n), dt, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(dt, dtype=np.int32)

    def get_reach_n_nodes(self, reach):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachNNodes(c_int(reach), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_reach_stream_nodes(self, reach):
        n = self.get_reach_n_nodes(reach)
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachStrmNodes(c_int(reach), c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_reach_gw_nodes(self, reach):
        n = self.get_reach_n_nodes(reach)
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachGWNodes(c_int(reach), c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_stream_bottom_elevations(self):
        n = self.n_stream_nodes
        elevs = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmBottomElevs(c_int(n), elevs, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(elevs, dtype=np.float64)

    def get_n_rating_table_points(self, stream_node):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNStrmRatingTablePoints(
            c_int(stream_node), byref(n), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return n.value

    def get_stream_rating_table(self, stream_node):
        n = self.get_n_rating_table_points(stream_node)
        stage = alloc_double(n)
        flow = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmRatingTable(
            c_int(stream_node), c_int(n), stage, flow, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(stage, dtype=np.float64), np.array(flow, dtype=np.float64)

    def get_stream_n_upstream_nodes(self, node):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmNUpstrmNodes(c_int(node), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_stream_upstream_nodes(self, node):
        n = self.get_stream_n_upstream_nodes(node)
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmUpstrmNodes(c_int(node), c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def is_stream_upstream_node(self, node1, node2):
        result = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_IsStrmUpstreamNode(
            c_int(node1), c_int(node2), byref(result), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return result.value == 1

    def get_reach_n_upstream_reaches(self, reach):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachNUpstrmReaches(c_int(reach), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_reach_upstream_reaches(self, reach):
        n = self.get_reach_n_upstream_reaches(reach)
        reaches = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetReachUpstrmReaches(
            c_int(reach), c_int(n), reaches, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(reaches, dtype=np.int32)

    # ==================================================================
    # Stream flow results (current timestep)
    # ==================================================================

    def _require_full_instantiation(self, what):
        """Fail fast for getters that read live simulation state.

        In inquiry mode the stream state and stream-GW connector arrays
        (e.g. ``StrmGWFlow``) are never allocated — only full
        instantiation creates them. Recent IWFM builds guard some of
        these paths and return a clean error, but older DLL builds
        (including the one shipped with this repo) dereference the
        unallocated arrays and crash the whole process with an access
        violation, so we refuse the call up front.
        """
        if self._is_for_inquiry:
            raise IWFMError(
                f"{what} requires a fully instantiated model: open with "
                "is_for_inquiry=False and run the simulation. In inquiry "
                "mode this data does not exist, and calling the DLL for it "
                "can crash Python with an access violation on older IWFM "
                "builds."
            )

    def _get_strm_array(self, func_name, factor=1.0):
        """Helper for stream node array getters (current-timestep state)."""
        self._require_full_instantiation(func_name.replace("IW_Model_Get", ""))
        n = self.n_stream_nodes
        buf = alloc_double(n)
        iStat = c_int(0)
        getattr(self._dll, func_name)(
            c_int(n), c_double(factor), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(buf, dtype=np.float64)

    def get_stream_flow(self, node, factor=1.0):
        self._require_full_instantiation("StrmFlow")
        flow = c_double(0.0)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmFlow(
            c_int(node), c_double(factor), byref(flow), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return flow.value

    def get_stream_flows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmFlows", factor)

    def get_stream_stages(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmStages", factor)

    def get_stream_gain_from_gw(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmGainFromGW", factor)

    def get_stream_gain_from_lakes(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmGainFromLakes", factor)

    def get_stream_tributary_inflows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmTributaryInflows", factor)

    def get_stream_rainfall_runoff(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmRainfallRunoff", factor)

    def get_stream_return_flows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmReturnFlows", factor)

    def get_stream_tile_drains(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmTileDrains", factor)

    def get_stream_pond_drains(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmPondDrains", factor)

    def get_stream_riparian_et(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmRiparianETs", factor)

    def get_stream_evaporation(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmEvap", factor)

    def get_stream_net_inflows_exc_divs_inflows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmNetInflows_ExcDivsInflows", factor)

    def get_stream_net_inflows_exc_divs_inflows_gw(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmNetInflows_ExcDivsInflowsGW", factor)

    def get_stream_wsa_flows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmWSAs", factor)

    def get_stream_net_bypass_inflows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmNetBypassInflows", factor)

    def get_stream_bypass_inflows(self, factor=1.0):
        return self._get_strm_array("IW_Model_GetStrmBypassInflows", factor)

    # ==================================================================
    # Stream inflows
    # ==================================================================

    def get_n_stream_inflows(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmNInflows(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_stream_inflow_nodes(self):
        n = self.get_n_stream_inflows()
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmInflowNodes(c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_stream_inflow_ids(self):
        n = self.get_n_stream_inflows()
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmInflowIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_stream_inflows_at(self, inflow_indices, factor=1.0):
        n = len(inflow_indices)
        idx = (c_int * n)(*inflow_indices)
        vals = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmInflows_AtSomeInflows(
            c_int(n), idx, c_double(factor), vals, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(vals, dtype=np.float64)

    # ==================================================================
    # Diversions
    # ==================================================================

    @property
    def n_diversions(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNDiversions(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_diversion_ids(self):
        n = self.n_diversions
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetDiversionIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_required_diversions(self, div_indices, factor=1.0):
        n = len(div_indices)
        idx = (c_int * n)(*div_indices)
        vals = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmRequiredDiversions_AtSomeDiversions(
            c_int(n), idx, c_double(factor), vals, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(vals, dtype=np.float64)

    def get_actual_diversions(self, div_indices, factor=1.0):
        n = len(div_indices)
        idx = (c_int * n)(*div_indices)
        vals = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmActualDiversions_AtSomeDiversions(
            c_int(n), idx, c_double(factor), vals, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(vals, dtype=np.float64)

    def get_diversion_export_nodes(self, div_indices):
        n = len(div_indices)
        idx = (c_int * n)(*div_indices)
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmDiversionsExportNodes(
            c_int(n), idx, nodes, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_diversion_n_elements(self, div):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmDiversionNElems(c_int(div), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_diversion_elements(self, div):
        n = self.get_diversion_n_elements(div)
        elems = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmDiversionElems(c_int(div), c_int(n), elems, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(elems, dtype=np.int32)

    def get_diversion_n_recharge_zone_elements(self, div):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmDiversionNRechargeZoneElems(
            c_int(div), byref(n), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return n.value

    def get_diversion_recharge_zone_elements(self, div):
        n = self.get_diversion_n_recharge_zone_elements(div)
        elems = alloc_int(n)
        fracs = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetStrmDiversionRechargeZoneElems(
            c_int(div), c_int(n), elems, fracs, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(elems, dtype=np.int32), np.array(fracs, dtype=np.float64)

    # ==================================================================
    # Bypasses
    # ==================================================================

    @property
    def n_bypasses(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNBypasses(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_bypass_ids(self):
        n = self.n_bypasses
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetBypassIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_bypass_export_nodes(self, bypass_indices):
        n = len(bypass_indices)
        idx = (c_int * n)(*bypass_indices)
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetBypassExportNodes(
            c_int(n), idx, nodes, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    def get_bypass_export_dest_data(self, bypass_indices):
        n = len(bypass_indices)
        idx = (c_int * n)(*bypass_indices)
        exp_nodes = alloc_int(n)
        dest_types = alloc_int(n)
        dests = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetBypassExportDestinationData(
            c_int(n), idx, exp_nodes, dest_types, dests, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return {
            "export_nodes": np.array(exp_nodes, dtype=np.int32),
            "dest_types": np.array(dest_types, dtype=np.int32),
            "destinations": np.array(dests, dtype=np.int32),
        }

    def get_bypass_outflows(self, factor=1.0):
        n = self.n_bypasses
        buf = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetBypassOutflows(
            c_int(n), c_double(factor), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(buf, dtype=np.float64)

    def get_bypass_recoverable_loss_factor(self, bypass):
        val = c_double(0.0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBypassRecoverableLossFactor(
            c_int(bypass), byref(val), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return val.value

    def get_bypass_non_recoverable_loss_factor(self, bypass):
        val = c_double(0.0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBypassNonRecoverableLossFactor(
            c_int(bypass), byref(val), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return val.value

    # ==================================================================
    # Lakes
    # ==================================================================

    @property
    def n_lakes(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNLakes(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_lake_ids(self):
        n = self.n_lakes
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetLakeIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_n_elements_in_lake(self, lake):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNElementsInLake(c_int(lake), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_elements_in_lake(self, lake):
        n = self.get_n_elements_in_lake(lake)
        elems = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetElementsInLake(c_int(lake), c_int(n), elems, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(elems, dtype=np.int32)

    # ==================================================================
    # Wells & pumping
    # ==================================================================

    @property
    def n_wells(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNWells(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    @property
    def n_elem_pumps(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNElemPumps(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_well_ids(self):
        n = self.n_wells
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetWellIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_well_coordinates(self):
        n = self.n_wells
        x = alloc_double(n)
        y = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetWellCoordinates(c_int(n), x, y, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(x, dtype=np.float64), np.array(y, dtype=np.float64)

    def get_well_perforation_top_bottom(self):
        n = self.n_wells
        top = alloc_double(n)
        bot = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetWellPerfTopBottom(c_int(n), top, bot, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(top, dtype=np.float64), np.array(bot, dtype=np.float64)

    def get_well_n_elements(self, well):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetWellNElems(c_int(well), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_well_elements(self, well):
        n = self.get_well_n_elements(well)
        elems = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetWellElems(c_int(well), c_int(n), elems, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(elems, dtype=np.int32)

    def get_elem_pump_ids(self):
        n = self.n_elem_pumps
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetElemPumpIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    # ==================================================================
    # Tile drains
    # ==================================================================

    def get_n_tile_drain_nodes(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNTileDrainNodes(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_tile_drain_ids(self):
        n = self.get_n_tile_drain_nodes()
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetTileDrainIDs(c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_tile_drain_nodes(self):
        n = self.get_n_tile_drain_nodes()
        nodes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetTileDrainNodes(c_int(n), nodes, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(nodes, dtype=np.int32)

    # ==================================================================
    # Hydrographs
    # ==================================================================

    def get_n_hydrograph_types(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNHydrographTypes(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_hydrograph_type_list(self):
        """Return list of dicts with 'name' and 'location_type'."""
        n = self.get_n_hydrograph_types()
        buf_len = n * 200
        buf = alloc_char(buf_len)
        loc_arr = alloc_int(n)
        loc_types = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetHydrographTypeList(
            c_int(n), loc_arr, c_int(buf_len), buf, loc_types, byref(iStat),
        )
        _check_status(iStat, self._dll)
        names = c_to_str_list(buf, loc_arr, n)
        return [{"name": names[i], "location_type": loc_types[i]}
                for i in range(n)]

    def get_n_hydrographs(self, location_type):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNHydrographs(c_int(location_type), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_hydrograph_ids(self, location_type):
        n = self.get_n_hydrographs(location_type)
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetHydrographIDs(c_int(location_type), c_int(n), ids, byref(iStat))
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_hydrograph_coordinates(self, location_type):
        n = self.get_n_hydrographs(location_type)
        x = alloc_double(n)
        y = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetHydrographCoordinates(
            c_int(location_type), c_int(n), x, y, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(x, dtype=np.float64), np.array(y, dtype=np.float64)

    def get_hydrograph(self, hyd_type, index, layer, begin_date, end_date,
                       interval, fact_lt=1.0, fact_vl=1.0):
        """Return (dates, values) for a hydrograph."""
        nt = self.n_timesteps
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        dates = alloc_double(nt)
        vals = alloc_double(nt)
        data_unit = c_int(0)
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetHydrograph(
            c_int(hyd_type), c_int(index), c_int(layer),
            d_len, c_begin, c_end, iv_len, c_intv,
            c_double(fact_lt), c_double(fact_vl),
            c_int(nt), dates, vals, byref(data_unit), byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = nt_out.value
        dates_arr = np.array(dates[:n], dtype=np.float64)
        vals_arr = np.array(vals[:n], dtype=np.float64)
        # The DLL reports the requested-window size, never the number of
        # entries actually read from the file. Unfilled date slots hold
        # zero Julian dates (-2415020.0 after the DLL's Julian->Excel
        # shift) and the corresponding VALUES are uninitialized memory,
        # so both arrays must be masked together by the date validity.
        valid = dates_arr > 0.0
        return dates_arr[valid], vals_arr[valid]

    # ==================================================================
    # Budget via model
    # ==================================================================

    def get_n_budgets(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_N(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_budget_list(self):
        """Return list of dicts with 'name', 'budget_type', 'location_type'."""
        n = self.get_n_budgets()
        if n == 0:
            return []
        buf_len = n * 200
        loc_arr = alloc_int(n)
        buf = alloc_char(buf_len)
        btypes = alloc_int(n)
        ltypes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_List(
            c_int(n), loc_arr, c_int(buf_len), buf, btypes, ltypes, byref(iStat),
        )
        _check_status(iStat, self._dll)
        names = c_to_str_list(buf, loc_arr, n)
        return [{"name": names[i], "budget_type": btypes[i],
                 "location_type": ltypes[i]} for i in range(n)]

    def get_budget_n_columns(self, budget_type, location):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_NColumns(
            c_int(budget_type), c_int(location), byref(n), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return n.value

    def get_budget_column_titles(self, budget_type, location,
                                 length_unit="FT", area_unit="SQ FT",
                                 volume_unit="CU FT"):
        n = self.get_budget_n_columns(budget_type, location)
        buf_len = n * 200
        u_len, c_lu = str_to_c(length_unit)
        _, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        loc_arr = alloc_int(n)
        buf = alloc_char(buf_len)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_ColumnTitles(
            c_int(budget_type), c_int(location), u_len,
            c_lu, c_au, c_vu, c_int(n), loc_arr,
            c_int(buf_len), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(buf, loc_arr, n)

    def get_budget_timeseries(self, budget_type, location, columns,
                              begin_date, end_date, interval,
                              fact_lt=1.0, fact_ar=1.0, fact_vl=1.0):
        """Read budget time-series data for selected columns at a location.

        Parameters
        ----------
        budget_type : int
            Budget type ID.
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
        dict
            ``dates``: np.ndarray, ``values``: np.ndarray shape (n_times, n_cols),
            ``data_types``: np.ndarray of int.
        """
        n_cols = len(columns)
        nt = self.n_timesteps
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        c_cols = (c_int * n_cols)(*columns)
        dates = alloc_double(nt)
        values = (c_double * (nt * n_cols))()
        dtypes = alloc_int(n_cols)
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_TSData(
            c_int(budget_type), c_int(location), c_int(n_cols), c_cols,
            d_len, c_begin, c_end, iv_len, c_intv,
            c_double(fact_lt), c_double(fact_ar), c_double(fact_vl),
            dates, c_int(nt), values, dtypes,
            byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = nt_out.value
        val_arr = np.frombuffer(values, dtype=np.float64).reshape(
            (nt, n_cols), order="F"
        )[:n, :].copy()
        return {
            "dates": np.array(dates[:n], dtype=np.float64),
            "values": val_arr,
            "data_types": np.array(dtypes, dtype=np.int32),
        }

    def get_budget_monthly_average(self, budget_type, location,
                                   begin_date, end_date,
                                   fact_vl=1.0, lu_type=0, swshed_comp=0):
        """Return monthly average flows."""
        max_flows = 200
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        flows = alloc_double(max_flows * 12)
        sd_flows = alloc_double(max_flows * 12)
        n_flows_out = c_int(0)
        name_buf_len = max_flows * 200
        name_buf = alloc_char(name_buf_len)
        loc_arr = alloc_int(max_flows)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_MonthlyAverageFlows(
            c_int(budget_type), c_int(location), c_int(lu_type),
            c_int(swshed_comp), d_len, c_begin, c_end,
            c_double(fact_vl), c_int(max_flows), flows, sd_flows,
            byref(n_flows_out), c_int(name_buf_len), name_buf,
            loc_arr, byref(iStat),
        )
        _check_status(iStat, self._dll)
        nf = n_flows_out.value
        names = c_to_str_list(name_buf, loc_arr, nf)
        flow_arr = np.frombuffer(flows, dtype=np.float64)[:nf * 12].reshape((nf, 12), order="F").copy()
        sd_arr = np.frombuffer(sd_flows, dtype=np.float64)[:nf * 12].reshape((nf, 12), order="F").copy()
        return {"names": names, "flows": flow_arr, "std_devs": sd_arr}

    def get_budget_annual(self, budget_type, location, begin_date, end_date,
                          fact_vl=1.0, lu_type=0, swshed_comp=0):
        """Return annual flows (water year)."""
        max_flows = 200
        max_times = 200
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        flows = alloc_double(max_flows * max_times)
        n_flows_out = c_int(0)
        n_times_out = c_int(0)
        name_buf_len = max_flows * 200
        name_buf = alloc_char(name_buf_len)
        loc_arr = alloc_int(max_flows)
        years = alloc_int(max_times)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_AnnualFlows(
            c_int(budget_type), c_int(location), c_int(lu_type),
            c_int(swshed_comp), d_len, c_begin, c_end,
            c_double(fact_vl), c_int(max_flows), c_int(max_times),
            flows, byref(n_flows_out), byref(n_times_out),
            c_int(name_buf_len), name_buf, loc_arr, years, byref(iStat),
        )
        _check_status(iStat, self._dll)
        nf = n_flows_out.value
        nt = n_times_out.value
        names = c_to_str_list(name_buf, loc_arr, nf)
        flow_arr = np.frombuffer(flows, dtype=np.float64)[:nf * nt].reshape((nf, nt), order="F").copy()
        return {"names": names, "flows": flow_arr,
                "years": np.array(years[:nt], dtype=np.int32)}

    def get_budget_annual_v2(self, budget_type, location, begin_date, end_date,
                             fact_vl=1.0, lu_type=0, swshed_comp=0,
                             calendar_year=False):
        """Return annual flows with calendar/water year option."""
        max_flows = 200
        max_times = 200
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        flows = alloc_double(max_flows * max_times)
        n_flows_out = c_int(0)
        n_times_out = c_int(0)
        name_buf_len = max_flows * 200
        name_buf = alloc_char(name_buf_len)
        loc_arr = alloc_int(max_flows)
        years = alloc_int(max_times)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_AnnualFlows_1(
            c_int(budget_type), c_int(location), c_int(lu_type),
            c_int(swshed_comp), d_len, c_begin, c_end,
            c_int(1 if calendar_year else 0),
            c_double(fact_vl), c_int(max_flows), c_int(max_times),
            flows, byref(n_flows_out), byref(n_times_out),
            c_int(name_buf_len), name_buf, loc_arr, years, byref(iStat),
        )
        _check_status(iStat, self._dll)
        nf = n_flows_out.value
        nt = n_times_out.value
        names = c_to_str_list(name_buf, loc_arr, nf)
        flow_arr = np.frombuffer(flows, dtype=np.float64)[:nf * nt].reshape((nf, nt), order="F").copy()
        return {"names": names, "flows": flow_arr,
                "years": np.array(years[:nt], dtype=np.int32)}

    def get_budget_cum_gw_storage_change(self, subregion, begin_date, end_date,
                                          interval, fact_vl=1.0):
        max_times = self.n_timesteps
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        dates = alloc_double(max_times)
        vals = alloc_double(max_times)
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_CumGWStorChange(
            c_int(subregion), d_len, c_begin, c_end, iv_len, c_intv,
            c_double(fact_vl), dates, c_int(max_times), vals,
            byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = nt_out.value
        return np.array(dates[:n], dtype=np.float64), np.array(vals[:n], dtype=np.float64)

    def get_budget_annual_cum_gw_storage_change(self, subregion, begin_date,
                                                 end_date, fact_vl=1.0):
        max_times = 200
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        vals = alloc_double(max_times)
        years = alloc_int(max_times)
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_AnnualCumGWStorChange(
            c_int(subregion), d_len, c_begin, c_end,
            c_double(fact_vl), c_int(max_times), vals, years,
            byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = nt_out.value
        return np.array(vals[:n], dtype=np.float64), np.array(years[:n], dtype=np.int32)

    def get_budget_annual_cum_gw_storage_change_v2(self, subregion, begin_date,
                                                    end_date, fact_vl=1.0,
                                                    calendar_year=False):
        max_times = 200
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        vals = alloc_double(max_times)
        years = alloc_int(max_times)
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetBudget_AnnualCumGWStorChange_1(
            c_int(subregion), d_len, c_begin, c_end,
            c_int(1 if calendar_year else 0),
            c_double(fact_vl), c_int(max_times), vals, years,
            byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = nt_out.value
        return np.array(vals[:n], dtype=np.float64), np.array(years[:n], dtype=np.int32)

    # ==================================================================
    # Zone budget via model
    # ==================================================================

    def get_n_zbudgets(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetZBudget_N(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_zbudget_list(self):
        n = self.get_n_zbudgets()
        if n == 0:
            return []
        buf_len = n * 200
        loc_arr = alloc_int(n)
        buf = alloc_char(buf_len)
        ztypes = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetZBudget_List(
            c_int(n), loc_arr, c_int(buf_len), buf, ztypes, byref(iStat),
        )
        _check_status(iStat, self._dll)
        names = c_to_str_list(buf, loc_arr, n)
        return [{"name": names[i], "zbudget_type": ztypes[i]} for i in range(n)]

    def get_zbudget_n_columns(self, zbudget_type, zone_id, zone_extent,
                               elements, layers, zone_ids):
        elements = np.asarray(elements, dtype=np.int32)
        layers = np.asarray(layers, dtype=np.int32)
        zone_ids_arr = np.asarray(zone_ids, dtype=np.int32)
        n_dim = len(elements)
        n_cols = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetZBudget_NColumns(
            c_int(zbudget_type), c_int(zone_id), c_int(zone_extent),
            c_int(n_dim),
            (c_int * n_dim)(*elements),
            (c_int * n_dim)(*layers),
            (c_int * n_dim)(*zone_ids_arr),
            byref(n_cols), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return n_cols.value

    def get_zbudget_column_titles(self, zbudget_type, zone_id, zone_extent,
                                   elements, layers, zone_ids,
                                   area_unit="SQ FT", volume_unit="CU FT"):
        elements = np.asarray(elements, dtype=np.int32)
        layers = np.asarray(layers, dtype=np.int32)
        zone_ids_arr = np.asarray(zone_ids, dtype=np.int32)
        n_dim = len(elements)
        n_cols = self.get_zbudget_n_columns(
            zbudget_type, zone_id, zone_extent, elements, layers, zone_ids_arr,
        )
        buf_len = n_cols * 200
        u_len, c_au = str_to_c(area_unit)
        _, c_vu = str_to_c(volume_unit)
        loc_arr = alloc_int(n_cols)
        buf = alloc_char(buf_len)
        iStat = c_int(0)
        self._dll.IW_Model_GetZBudget_ColumnTitles(
            c_int(zbudget_type), c_int(zone_id), c_int(zone_extent),
            c_int(n_dim),
            (c_int * n_dim)(*elements),
            (c_int * n_dim)(*layers),
            (c_int * n_dim)(*zone_ids_arr),
            u_len, c_au, c_vu,
            c_int(n_cols), loc_arr, c_int(buf_len), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(buf, loc_arr, n_cols)

    def get_zbudget_timeseries(self, zbudget_type, zone_id, columns,
                               zone_extent, elements, layers, zone_ids,
                               begin_date, end_date, interval,
                               fact_ar=1.0, fact_vl=1.0):
        """Read Z-Budget time-series data for a zone.

        Parameters
        ----------
        zbudget_type : int
            Z-Budget type ID.
        zone_id : int
            Zone number.
        columns : list[int]
            1-based column indices.
        zone_extent : int
            Zone extent ID.
        elements, layers, zone_ids : array-like of int
            Element, layer, and zone assignment arrays.
        begin_date, end_date : str
            Date-time strings.
        interval : str
            Output interval.

        Returns
        -------
        dict
            ``dates``: np.ndarray, ``values``: np.ndarray shape (n_times, n_cols),
            ``data_types``: np.ndarray of int.
        """
        elements = np.asarray(elements, dtype=np.int32)
        layers = np.asarray(layers, dtype=np.int32)
        zone_ids_arr = np.asarray(zone_ids, dtype=np.int32)
        n_dim = len(elements)
        n_cols = len(columns)
        nt = self.n_timesteps
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        iv_len, c_intv = str_to_c(interval)
        c_cols = (c_int * n_cols)(*columns)
        dates = alloc_double(nt)
        values = (c_double * (nt * n_cols))()
        dtypes = alloc_int(n_cols)
        nt_out = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetZBudget_TSData(
            c_int(zbudget_type), c_int(zone_id), c_int(n_cols), c_cols,
            c_int(zone_extent), c_int(n_dim),
            (c_int * n_dim)(*elements),
            (c_int * n_dim)(*layers),
            (c_int * n_dim)(*zone_ids_arr),
            d_len, c_begin, c_end, iv_len, c_intv,
            c_double(fact_ar), c_double(fact_vl),
            dates, c_int(nt), values, dtypes,
            byref(nt_out), byref(iStat),
        )
        _check_status(iStat, self._dll)
        n = nt_out.value
        val_arr = np.frombuffer(values, dtype=np.float64).reshape(
            (nt, n_cols), order="F"
        )[:n, :].copy()
        return {
            "dates": np.array(dates[:n], dtype=np.float64),
            "values": val_arr,
            "data_types": np.array(dtypes, dtype=np.int32),
        }

    # ==================================================================
    # Water demand & supply
    # ==================================================================

    def get_future_water_demand_for_diversion(self, div, date, factor=1.0):
        d_len, c_date = str_to_c(date)
        demand = c_double(0.0)
        iStat = c_int(0)
        self._dll.IW_Model_GetFutureWaterDemand_ForDiversion(
            c_int(div), d_len, c_date, c_double(factor),
            byref(demand), byref(iStat),
        )
        _check_status(iStat, self._dll)
        return demand.value

    def get_supply_purpose(self, supply_type, supplies):
        n = len(supplies)
        idx = (c_int * n)(*supplies)
        result = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetSupplyPurpose(
            c_int(supply_type), c_int(n), idx, result, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(result, dtype=np.int32)

    def _get_supply_req_or_short(self, func_name, loc_type, locations, factor):
        n = len(locations)
        idx = (c_int * n)(*locations)
        vals = alloc_double(n)
        iStat = c_int(0)
        getattr(self._dll, func_name)(
            c_int(loc_type), c_int(n), idx, c_double(factor), vals, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(vals, dtype=np.float64)

    def get_supply_requirement_ag(self, location_type, locations, factor=1.0):
        return self._get_supply_req_or_short(
            "IW_Model_GetSupplyRequirement_Ag", location_type, locations, factor,
        )

    def get_supply_requirement_urban(self, location_type, locations, factor=1.0):
        return self._get_supply_req_or_short(
            "IW_Model_GetSupplyRequirement_Urb", location_type, locations, factor,
        )

    def get_supply_short_at_origin_ag(self, supply_type, supplies, factor=1.0):
        return self._get_supply_req_or_short(
            "IW_Model_GetSupplyShortAtOrigin_Ag", supply_type, supplies, factor,
        )

    def get_supply_short_at_origin_urban(self, supply_type, supplies, factor=1.0):
        return self._get_supply_req_or_short(
            "IW_Model_GetSupplyShortAtOrigin_Urb", supply_type, supplies, factor,
        )

    def get_subregion_ag_pumping_avg_depth_to_gw(self):
        n = self.n_subregions
        buf = alloc_double(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetSubregionAgPumpingAverageDepthToGW(
            c_int(n), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(buf, dtype=np.float64)

    def get_zone_ag_pumping_avg_depth_to_gw(self, elements, zones, n_zones):
        elements = np.asarray(elements, dtype=np.int32)
        zones_arr = np.asarray(zones, dtype=np.int32)
        n_elems = len(elements)
        buf = alloc_double(n_zones)
        iStat = c_int(0)
        self._dll.IW_Model_GetZoneAgPumpingAverageDepthToGW(
            c_int(n_elems),
            (c_int * n_elems)(*elements),
            (c_int * n_elems)(*zones_arr),
            c_int(n_zones), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(buf, dtype=np.float64)

    def get_n_ag_crops(self):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNAgCrops(byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_land_use_areas(self, begin_date, end_date, lu_type, lu,
                           n_elements=None, fact_area=1.0):
        """Return land use areas, shape (n_elements, n_times)."""
        if n_elements is None:
            n_elements = self.n_elements
        n_times = self.n_timesteps
        d_len, c_begin = str_to_c(begin_date)
        _, c_end = str_to_c(end_date)
        buf = alloc_double(n_elements * n_times)
        iStat = c_int(0)
        self._dll.IW_Model_GetLandUseAreasForTimePeriod(
            d_len, c_begin, c_end, c_int(lu_type), c_int(lu),
            c_int(n_elements), c_int(n_times), c_double(fact_area),
            buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.frombuffer(buf, dtype=np.float64).reshape(
            (n_elements, n_times), order="F"
        ).copy()

    # ==================================================================
    # Generic location queries
    # ==================================================================

    def get_n_locations(self, location_type):
        n = c_int(0)
        iStat = c_int(0)
        self._dll.IW_Model_GetNLocations(c_int(location_type), byref(n), byref(iStat))
        _check_status(iStat, self._dll)
        return n.value

    def get_location_ids(self, location_type):
        n = self.get_n_locations(location_type)
        ids = alloc_int(n)
        iStat = c_int(0)
        self._dll.IW_Model_GetLocationIDs(
            c_int(location_type), c_int(n), ids, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return np.array(ids, dtype=np.int32)

    def get_names(self, location_type):
        n = self.get_n_locations(location_type)
        buf_len = n * 100
        loc_arr = alloc_int(n)
        buf = alloc_char(buf_len)
        iStat = c_int(0)
        self._dll.IW_Model_GetNames(
            c_int(location_type), c_int(n), loc_arr,
            c_int(buf_len), buf, byref(iStat),
        )
        _check_status(iStat, self._dll)
        return c_to_str_list(buf, loc_arr, n)

    # ==================================================================
    # DataFrame-returning methods (interchangeable with IO layer)
    # ==================================================================

    def _excel_dates_to_index(self, dates):
        """Convert Excel serial date array to pandas DatetimeIndex."""
        from datetime import datetime, timedelta
        base = datetime(1899, 12, 30)
        dts = [base + timedelta(days=float(d)) for d in dates if d > 0]
        return pd.DatetimeIndex(dts)

    # -- Grid geometry (cached) ----------------------------------------

    def nodes_df(self):
        """Return GeoDataFrame of nodes: node_id, x, y, geometry(Point)."""
        if "nodes" in self._cache:
            return self._cache["nodes"]
        ids = self.get_node_ids()
        x, y = self.get_node_coordinates()
        df = pd.DataFrame({"node_id": ids, "x": x, "y": y})
        if _HAS_GEO:
            geom = [Point(xi, yi) for xi, yi in zip(x, y)]
            df = gpd.GeoDataFrame(df, geometry=geom)
        self._cache["nodes"] = df
        return df

    def elements_df(self):
        """Return GeoDataFrame of elements: element_id, node1-4, subregion, geometry(Polygon)."""
        if "elements" in self._cache:
            return self._cache["elements"]
        elem_ids = self.get_element_ids()
        subs = self.get_element_subregions()
        configs = []
        for eid in elem_ids:
            configs.append(self.get_element_config(int(eid)))
        n1 = [int(c[0]) for c in configs]
        n2 = [int(c[1]) for c in configs]
        n3 = [int(c[2]) for c in configs]
        n4 = [int(c[3]) for c in configs]
        df = pd.DataFrame({
            "element_id": elem_ids, "node1": n1, "node2": n2,
            "node3": n3, "node4": n4, "subregion": subs,
        })
        if _HAS_GEO:
            ndf = self.nodes_df()
            coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
            polys = []
            for _, row in df.iterrows():
                nodes = [row["node1"], row["node2"], row["node3"]]
                if row["node4"] != 0:
                    nodes.append(row["node4"])
                coords = [coord[n] for n in nodes]
                coords.append(coords[0])
                polys.append(Polygon(coords))
            df = gpd.GeoDataFrame(df, geometry=polys)
        self._cache["elements"] = df
        return df

    def subregions_df(self):
        """Return DataFrame: subregion_id, name."""
        if "subregions" in self._cache:
            return self._cache["subregions"]
        ids = self.get_subregion_ids()
        names = [self.get_subregion_name(int(sid)) for sid in ids]
        df = pd.DataFrame({"subregion_id": ids, "name": names})
        self._cache["subregions"] = df
        return df

    def stratigraphy_df(self):
        """Return DataFrame: node_id, elevation, aquitard_1, aquifer_1, ..."""
        if "strata" in self._cache:
            return self._cache["strata"]
        node_ids = self.get_node_ids()
        gse = self.get_ground_surface_elevation()
        tops = self.get_aquifer_top_elevation()
        bots = self.get_aquifer_bottom_elevation()
        nl = self.n_layers
        data = {"node_id": node_ids, "elevation": gse}
        for i in range(nl):
            data[f"aquitard_{i+1}"] = tops[:, i]
            data[f"aquifer_{i+1}"] = bots[:, i]
        df = pd.DataFrame(data)
        self._cache["strata"] = df
        return df

    # -- Stream network (cached) ---------------------------------------

    def reaches_df(self):
        """Return DataFrame: reach_id, n_nodes, outflow_dest, name."""
        if "reaches" in self._cache:
            return self._cache["reaches"]
        rids = self.get_reach_ids()
        out_dest = self.get_reach_outflow_destinations()
        rows = []
        for i, rid in enumerate(rids):
            n_sn = self.get_reach_n_nodes(int(rid))
            rows.append({
                "reach_id": int(rid),
                "n_nodes": n_sn,
                "outflow_dest": int(out_dest[i]),
                "name": "",
            })
        df = pd.DataFrame(rows)
        self._cache["reaches"] = df
        return df

    def stream_nodes_df(self):
        """Return GeoDataFrame: stream_node_id, reach_id, gw_node_id, geometry(Point)."""
        if "stream_nodes" in self._cache:
            return self._cache["stream_nodes"]
        rids = self.get_reach_ids()
        rows = []
        for rid in rids:
            sn = self.get_reach_stream_nodes(int(rid))
            gn = self.get_reach_gw_nodes(int(rid))
            for s, g in zip(sn, gn):
                rows.append({
                    "stream_node_id": int(s),
                    "reach_id": int(rid),
                    "gw_node_id": int(g),
                })
        df = pd.DataFrame(rows)
        if _HAS_GEO:
            ndf = self.nodes_df()
            coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
            geom = []
            for _, row in df.iterrows():
                gw_id = row["gw_node_id"]
                if gw_id in coord:
                    geom.append(Point(*coord[gw_id]))
                else:
                    geom.append(None)
            df = gpd.GeoDataFrame(df, geometry=geom)
        self._cache["stream_nodes"] = df
        return df

    def stream_rating_tables_df(self):
        """Return DataFrame: stream_node_id, bottom_elev, stage, flow."""
        if "rating_tables" in self._cache:
            return self._cache["rating_tables"]
        sn_ids = self.get_stream_node_ids()
        bot_elevs = self.get_stream_bottom_elevations()
        rows = []
        for i, sn_id in enumerate(sn_ids):
            stage, flow = self.get_stream_rating_table(int(sn_id))
            for s, f in zip(stage, flow):
                rows.append({
                    "stream_node_id": int(sn_id),
                    "bottom_elev": bot_elevs[i],
                    "stage": s,
                    "flow": f,
                })
        df = pd.DataFrame(rows)
        self._cache["rating_tables"] = df
        return df

    # -- Lakes, diversions, bypasses, tile drains, wells ---------------

    def lakes_df(self):
        """Return DataFrame: lake_id, n_elements, elements(list)."""
        if "lakes" in self._cache:
            return self._cache["lakes"]
        lids = self.get_lake_ids()
        rows = []
        for lid in lids:
            elems = self.get_elements_in_lake(int(lid))
            rows.append({
                "lake_id": int(lid),
                "n_elements": len(elems),
                "elements": elems.tolist(),
            })
        df = pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["lake_id", "n_elements", "elements"])
        self._cache["lakes"] = df
        return df

    def diversions_df(self):
        """Return DataFrame: diversion_id, export_node, n_elements, elements(list)."""
        if "diversions" in self._cache:
            return self._cache["diversions"]
        dids = self.get_diversion_ids()
        if len(dids) == 0:
            df = pd.DataFrame(
                columns=["diversion_id", "export_node", "n_elements", "elements"])
            self._cache["diversions"] = df
            return df
        exp_nodes = self.get_diversion_export_nodes(dids.tolist())
        rows = []
        for i, did in enumerate(dids):
            elems = self.get_diversion_elements(int(did))
            rows.append({
                "diversion_id": int(did),
                "export_node": int(exp_nodes[i]),
                "n_elements": len(elems),
                "elements": elems.tolist(),
            })
        df = pd.DataFrame(rows)
        self._cache["diversions"] = df
        return df

    def bypasses_df(self):
        """Return DataFrame: bypass_id, export_node, dest_type, dest, rec_loss, nonrec_loss."""
        if "bypasses" in self._cache:
            return self._cache["bypasses"]
        bids = self.get_bypass_ids()
        if len(bids) == 0:
            df = pd.DataFrame(columns=[
                "bypass_id", "export_node", "dest_type", "dest",
                "rec_loss", "nonrec_loss"])
            self._cache["bypasses"] = df
            return df
        dest_data = self.get_bypass_export_dest_data(bids.tolist())
        rows = []
        for i, bid in enumerate(bids):
            rows.append({
                "bypass_id": int(bid),
                "export_node": int(dest_data["export_nodes"][i]),
                "dest_type": int(dest_data["dest_types"][i]),
                "dest": int(dest_data["destinations"][i]),
                "rec_loss": self.get_bypass_recoverable_loss_factor(int(bid)),
                "nonrec_loss": self.get_bypass_non_recoverable_loss_factor(int(bid)),
            })
        df = pd.DataFrame(rows)
        self._cache["bypasses"] = df
        return df

    def tile_drains_df(self):
        """Return GeoDataFrame: id, node, x, y, geometry(Point)."""
        if "tile_drains" in self._cache:
            return self._cache["tile_drains"]
        n_td = self.get_n_tile_drain_nodes()
        if n_td == 0:
            df = pd.DataFrame(columns=["id", "node", "x", "y"])
            self._cache["tile_drains"] = df
            return df
        td_ids = self.get_tile_drain_ids()
        td_nodes = self.get_tile_drain_nodes()
        ndf = self.nodes_df()
        coord = {int(r["node_id"]): (r["x"], r["y"]) for _, r in ndf.iterrows()}
        rows = []
        for tid, nid in zip(td_ids, td_nodes):
            xy = coord.get(int(nid), (np.nan, np.nan))
            rows.append({"id": int(tid), "node": int(nid), "x": xy[0], "y": xy[1]})
        df = pd.DataFrame(rows)
        if _HAS_GEO:
            geom = [Point(r["x"], r["y"]) if not np.isnan(r["x"]) else None
                    for _, r in df.iterrows()]
            df = gpd.GeoDataFrame(df, geometry=geom)
        self._cache["tile_drains"] = df
        return df

    def wells_df(self):
        """Return GeoDataFrame: well_id, x, y, perf_top, perf_bot, geometry(Point)."""
        if "wells" in self._cache:
            return self._cache["wells"]
        n = self.n_wells
        if n == 0:
            df = pd.DataFrame(
                columns=["well_id", "x", "y", "perf_top", "perf_bot"])
            self._cache["wells"] = df
            return df
        ids = self.get_well_ids()
        x, y = self.get_well_coordinates()
        top, bot = self.get_well_perforation_top_bottom()
        df = pd.DataFrame({
            "well_id": ids, "x": x, "y": y,
            "perf_top": top, "perf_bot": bot,
        })
        if _HAS_GEO:
            geom = [Point(xi, yi) for xi, yi in zip(x, y)]
            df = gpd.GeoDataFrame(df, geometry=geom)
        self._cache["wells"] = df
        return df

    # -- Time-series results -------------------------------------------

    def heads_df(self, layer, begin_date=None, end_date=None):
        """Return DataFrame(DatetimeIndex) with one column per node.

        Parameters
        ----------
        layer : int
            1-based layer index.
        begin_date, end_date : str, optional
            IWFM date strings. Defaults to full simulation period.
        """
        ts = self.get_time_specs()
        if begin_date is None:
            begin_date = ts["dates"][0]
        if end_date is None:
            end_date = ts["dates"][-1]
        dates, heads = self.get_gw_heads_for_layer(layer, begin_date, end_date)
        idx = self._excel_dates_to_index(dates)
        node_ids = self.get_node_ids()
        cols = [f"node_{int(nid)}" for nid in node_ids]
        # heads shape: (n_nodes, n_times) -> transpose to (n_times, n_nodes)
        return pd.DataFrame(heads[:, :len(idx)].T, index=idx, columns=cols)

    def subsidence_df(self, factor=1.0):
        """Return DataFrame of current-timestep subsidence: node_id, layer_1, ..., layer_N."""
        data = self.get_subsidence_all(factor=factor)
        node_ids = self.get_node_ids()
        cols = {f"layer_{i+1}": data[:, i] for i in range(data.shape[1])}
        cols["node_id"] = node_ids
        df = pd.DataFrame(cols)
        # Reorder: node_id first
        col_order = ["node_id"] + [f"layer_{i+1}" for i in range(data.shape[1])]
        return df[col_order]

    def budget_df(self, budget_type, location, begin_date=None, end_date=None,
                  interval=None, columns=None, fact_lt=1.0, fact_ar=1.0,
                  fact_vl=1.0):
        """Return DataFrame(DatetimeIndex) of budget time series.

        Parameters
        ----------
        budget_type : int
        location : int
            1-based location index.
        columns : list[int], optional
            1-based column indices. Default: all columns.
        """
        ts = self.get_time_specs()
        if begin_date is None:
            begin_date = ts["dates"][0]
        if end_date is None:
            end_date = ts["dates"][-1]
        if interval is None:
            interval = ts["interval"]
        if columns is None:
            n_cols = self.get_budget_n_columns(budget_type, location)
            columns = list(range(1, n_cols + 1))
        titles = self.get_budget_column_titles(budget_type, location)
        raw = self.get_budget_timeseries(
            budget_type, location, columns, begin_date, end_date, interval,
            fact_lt=fact_lt, fact_ar=fact_ar, fact_vl=fact_vl,
        )
        idx = self._excel_dates_to_index(raw["dates"])
        # titles[0] is 'Time', skip it; columns are 1-based matching titles[1:]
        col_names = [titles[c] if c < len(titles) else f"col_{c}"
                     for c in columns]
        return pd.DataFrame(raw["values"][:len(idx)], index=idx, columns=col_names)

    def hydrograph_df(self, hyd_type, index, layer, begin_date=None,
                      end_date=None, interval=None, fact_lt=1.0, fact_vl=1.0):
        """Return DataFrame(DatetimeIndex) with a single 'value' column."""
        ts = self.get_time_specs()
        if begin_date is None:
            begin_date = ts["dates"][0]
        if end_date is None:
            end_date = ts["dates"][-1]
        if interval is None:
            interval = ts["interval"]
        dates, vals = self.get_hydrograph(
            hyd_type, index, layer, begin_date, end_date, interval,
            fact_lt=fact_lt, fact_vl=fact_vl,
        )
        # Filter out invalid dates
        mask = dates > 0
        idx = self._excel_dates_to_index(dates[mask])
        return pd.DataFrame({"value": vals[mask][:len(idx)]}, index=idx)

    def stream_flows_df(self, factor=1.0):
        """Return DataFrame of current-timestep stream flow components.

        Columns: stream_node_id, flow, stage, gain_from_gw,
        gain_from_lakes, tributary_inflows, return_flows,
        tile_drains, rainfall_runoff, riparian_et, evaporation.
        """
        sn_ids = self.get_stream_node_ids()
        df = pd.DataFrame({
            "stream_node_id": sn_ids,
            "flow": self.get_stream_flows(factor),
            "stage": self.get_stream_stages(factor),
            "gain_from_gw": self.get_stream_gain_from_gw(factor),
            "gain_from_lakes": self.get_stream_gain_from_lakes(factor),
            "tributary_inflows": self.get_stream_tributary_inflows(factor),
            "return_flows": self.get_stream_return_flows(factor),
            "tile_drains": self.get_stream_tile_drains(factor),
            "rainfall_runoff": self.get_stream_rainfall_runoff(factor),
            "riparian_et": self.get_stream_riparian_et(factor),
            "evaporation": self.get_stream_evaporation(factor),
        })
        return df

    def supply_demand_df(self, location_type, locations, factor=1.0):
        """Return DataFrame: location_id, ag_requirement, urban_requirement, ag_shortage, urban_shortage."""
        locs = list(locations)
        ag_req = self.get_supply_requirement_ag(location_type, locs, factor)
        urb_req = self.get_supply_requirement_urban(location_type, locs, factor)
        ag_short = self.get_supply_short_at_origin_ag(location_type, locs, factor)
        urb_short = self.get_supply_short_at_origin_urban(location_type, locs, factor)
        return pd.DataFrame({
            "location_id": locs,
            "ag_requirement": ag_req,
            "urban_requirement": urb_req,
            "ag_shortage": ag_short,
            "urban_shortage": urb_short,
        })
