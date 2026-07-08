# DLL Bug: Missing Return Flow Section Skip

## Summary

Two subroutines in `Class_AppGW.f90` fail to skip the Groundwater Return Flow section when re-reading `GW_MAIN.dat` from disk. This causes `ReadInitialHeads` to start reading from the wrong file position, producing a spurious "Node ID 1 is listed more than once for initial groundwater heads" fatal error.

## Affected Functions

Both subroutines are used exclusively in **inquiry mode** (`lModel_ForInquiry_Defined = .TRUE.`), where the DLL re-reads the GW file from scratch rather than using cached values.

1. **`GetAquiferParameters_FromFile`** (line ~1877) — called by all individual aquifer parameter getters in inquiry mode (`GetAquiferKh_FromFile`, `GetAquiferSy_FromFile`, etc.)
2. **`GetGWHeadsIC`** (line ~1577) — called by `IW_Model_GetGWHeadsIC`

## File Location

`source_code/SourceCode/IWFM-kernel/Package_AppGW/Class_AppGW.f90`

## Root Cause

The `GW_MAIN.dat` file has three sections in sequence after aquifer parameters:

```
Section A:  Anomaly Hydraulic Conductivity   (NEBK, FACT, TUNITH, then NEBK data lines)
Section B:  Groundwater Return Flow          (IFLAGRF, then node data if IFLAGRF=1)
Section C:  Initial Groundwater Head Values  (FACTHP, then NNodes data lines)
```

The **model constructor** (`AppGW%New`, line ~668) correctly reads all three sections:

```fortran
CALL ReadAquiferParameters(...)                          ! reads Section A internally
CALL AppGWParamFile%ReadData(iGWReturnFlowDataFlag,...)  ! reads IFLAGRF from Section B
IF (iGWReturnFlowDataFlag .EQ. 1) ...                    ! reads Section B data if enabled
CALL ReadInitialHeads(...)                               ! reads Section C -- correct position
```

But **`GetAquiferParameters_FromFile`** (line ~1877) skips Section B entirely:

```fortran
CALL ReadAquiferParameters(...)   ! reads Section A internally
CALL ReadInitialHeads(...)        ! file pointer is at Section B, NOT Section C
```

And **`GetGWHeadsIC`** (line ~1577) also skips Section B:

```fortran
! Skip anomaly hydraulic conductivities (Section A)
CALL vGWMainFile%ReadData(iNData,iStat)
DO indx=1,iNData+2
    CALL vGWMainFile%ReadData(ALine,iStat)
END DO
! "Now, we are at initial conditions" -- WRONG, we are at Section B
CALL ReadInitialHeads(...)
```

## What Happens

With a typical `GW_MAIN.dat` where `NEBK=0` and `IFLAGRF=0`, the file after aquifer parameters looks like:

```
     0                          / NEBK        ← Section A start
     1.0                        / FACT
     1day                       / TUNITH
*                                             ← Section A trailing lines
*
     0                          / IFLAGRF     ← Section B start (SKIPPED)
*
*
     1.0                        / FACTHP      ← Section C start
     1     280.0    290.0                     ← Node 1
     2     280.0    290.0
     ...
```

Because Section B is never consumed, `ReadInitialHeads` starts reading from `IFLAGRF=0`. The Fortran free-format reader then:

1. Reads `0` (IFLAGRF) as the conversion factor `rFactor`
2. Skips the two `*` lines (treated as comments)
3. Reads `1.0  / FACTHP` as the first node line — interprets `1` as Node ID 1
4. Reads the actual `1  280.0  290.0` line — Node ID 1 again
5. Raises: `Node ID 1 is listed more than once for initial groundwater heads!`

## Fix

Add return flow section skipping in both subroutines, mirroring the logic in the constructor.

### In `GetAquiferParameters_FromFile` (between `ReadAquiferParameters` and `ReadInitialHeads`):

```fortran
CALL ReadAquiferParameters(iNLayers,AppGrid,TimeStep,AppGWParamFile,cVarTimeUnit,Nodes,iStat)
IF (iStat .EQ. -1) GOTO 10

! --- ADD: Skip groundwater return flow section ---
CALL AppGWParamFile%ReadData(iNSkip,iStat)  ;  IF (iStat .EQ. -1) GOTO 10   ! IFLAGRF
IF (iNSkip .EQ. 1) THEN
    CALL AppGWParamFile%ReadData(iNSkip,iStat)  ;  IF (iStat .EQ. -1) GOTO 10   ! NNodes count
    DO indx=1,iNSkip
        CALL AppGWParamFile%ReadData(cALine,iStat)  ;  IF (iStat .EQ. -1) GOTO 10
    END DO
END IF
! --- END ADD ---

!Initial conditions
CALL ReadInitialHeads(AppGWParamFile,iNNodes,iGWNodeIDs,Stratigraphy,rHeads,iStat)
```

### In `GetGWHeadsIC` (between the anomaly KC skip and `ReadInitialHeads`):

```fortran
!Skip anomaly hydraulic conductivities
CALL vGWMainFile%ReadData(iNData,iStat)  ;  IF (iStat .NE. 0) RETURN
DO indx=1,iNData+2
    CALL vGWMainFile%ReadData(ALine,iStat)
    IF (iStat .NE. 0) RETURN
END DO

! --- ADD: Skip groundwater return flow section ---
CALL vGWMainFile%ReadData(iNData,iStat)  ;  IF (iStat .NE. 0) RETURN   ! IFLAGRF
IF (iNData .EQ. 1) THEN
    CALL vGWMainFile%ReadData(iNData,iStat)  ;  IF (iStat .NE. 0) RETURN   ! NNodes count
    DO indx=1,iNData
        CALL vGWMainFile%ReadData(ALine,iStat)  ;  IF (iStat .NE. 0) RETURN
    END DO
END IF
! --- END ADD ---

!Now, we are at initial conditions
iNNodes = SIZE(iNodeIDs)
CALL ReadInitialHeads(vGWMainFile,iNNodes,iNodeIDs,Stratigraphy,rGWHeadsIC,iStat)
```

Note: The exact skip logic for the return flow section (when `IFLAGRF=1`) should match what `ReadGWReturnFlowDestinations` consumes in the constructor. Verify the line count against the constructor's read pattern at line ~674-689.

## Impact

This bug affects **all inquiry-mode calls** that read aquifer parameters or initial heads:

- `model.get_gw_heads_initial()`
- `model.get_aquifer_horizontal_k()`
- `model.get_aquifer_vertical_k()`
- `model.get_aquifer_specific_yield()`
- `model.get_aquifer_specific_storage()`
- `model.get_aquitard_vertical_k()`
- `model.get_aquifer_parameters()`

In normal (non-inquiry) mode, these functions return cached values and do not re-read the file, so the bug does not manifest.
