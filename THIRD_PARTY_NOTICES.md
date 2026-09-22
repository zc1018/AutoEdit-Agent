# Third-Party Notices

## DaVinci Resolve MCP

This repository includes an original operational skill that documents how to
use `davinci-resolve-mcp`. The MCP server itself is installed from its upstream
package and is not vendored here.

- Project: https://github.com/samuelgursky/davinci-resolve-mcp
- Copyright: 2025-2026 DaVinci Resolve MCP Contributors
- License: MIT

DaVinci Resolve is a product of Blackmagic Design. This project is not
affiliated with or endorsed by Blackmagic Design.


## macOS Jianying draft compatibility references

The macOS Jianying adapter uses pyJianYingDraft as an external base serializer and
contains independently implemented compatibility transformations for the macOS
desktop draft layout (`draft_info.json`, Mac platform metadata, media-pool registration,
and draft-local `Resources/` bundling).

Compatibility behavior was cross-checked against:
- https://github.com/GuanYixuan/pyJianYingDraft — Apache-2.0
- https://github.com/luoluoluo22/jianying-editor-skill — MIT; vendors pyJianYingDraft under Apache-2.0
- https://github.com/Vincentwei1021/video-shotcraft — macOS Jianying interoperability reference

No Jianying application binaries, device identifiers, user drafts, or third-party media
are bundled in this repository.
