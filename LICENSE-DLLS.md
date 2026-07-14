# License of the redistributed IWFM DLL builds

The `iwfm-io` Python code is licensed under Apache-2.0 (see `LICENSE`).
The compiled IWFM DLLs published as GitHub release assets on this project
(tags `dll-<version>`, e.g. `dll-2025.0.1747`) are **not** part of that
license: they are unmodified redistributions of software written and
released by the California Department of Water Resources (DWR) under the
**GNU General Public License v2.0**.

- **What the assets are.** Each `dll-<version>` release contains
  `IWFM_C_x64-<version>.zip` (the compiled `IWFM_C_x64.dll`, exactly as
  built by DWR and obtained from DWR's release archive on the CNRA Open
  Data portal) and `iwfm-source-<version>.zip` (the corresponding IWFM
  Fortran source code for that build).
- **Corresponding source.** GPL-2.0 requires that redistributed binaries
  be accompanied by their source. Every `dll-<version>` release asset
  must therefore include, or link to, the corresponding IWFM source zip.
  When publishing a new DLL build, always attach both zips to the release.
- **What downloading means for you.** Fetching a DLL with
  `iwfm_io.dll.download_dll()` (or manually from the releases page) means
  you receive that DLL under GPL-2.0. The GPL governs the DLL itself —
  copying, modifying, or redistributing it. It imposes no obligations on
  programs that merely call the DLL's C API at the user's direction, so
  using `iwfm-io` (Apache-2.0) together with a locally installed IWFM DLL
  does not place your own code under the GPL.
- **Copyright.** IWFM, including the DLL builds, is Copyright California
  Department of Water Resources.
