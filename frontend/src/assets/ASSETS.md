# ElderCare Vision artwork

## Incidents reference canvas (2026-10-04)

- `incidents-reference-canvas.png`: built-in imagegen, 2172x724, generated and visually inspected before implementation. Prompt: reproduce only the supplied reference's faint top-right frosted white security camera and soft pale blue curved forms; leave the left two thirds nearly empty; exclude UI, text, cards, controls, numbers, people and footage. The original generated image is preserved. This is decorative CSS background art, never incident evidence. Queue thumbnails come from saved evidence IDs through the existing API.

## Signup reference refresh (2026-10-03)

- `signup-reference-v3.png`: built-in imagegen using the newly supplied signup screenshot as composition reference. Opaque synthetic bright home, white blue-lens camera, tall blue glass pose panel and blue/mint edge ribbons. Prompt removed navigation, logos, headings, UI panels, text, form controls and buttons, leaving quiet areas for native HTML. Artwork was generated and inspected before coding, then copied into the project with the original preserved. The pose is decorative illustration, not measured keypoints or detector evidence; no Safe status or clinical assessment is asserted. Existing assets retained.

## Sign-in reference follow-up (2026-10-03)

- `signin-reference-v2.png`: built-in imagegen, 1586 x 992 opaque decorative background. Prompt: match the supplied camera/blue beam/pose/phone/home/glass-ribbon scene; remove the navigation, headline, form card, controls and privacy row; keep the right 40 percent pale and quiet and the lower-left area clear for real HTML. The image's device/pose/activity labels are synthetic illustration, not detector evidence. All functional page controls and the headline remain live HTML. Original generated image and previous `signin-art.png` are preserved.
- `google-mark.png`: Google's official G artwork, downloaded from https://developers.google.com/static/identity/images/g-logo.png on 2026-10-03. Source: https://developers.google.com/identity/branding-guidelines. Google trademark ownership is retained. Preserved but unused after the user requested removal of the Google button and divider; OAuth is not integrated.


Generated with the built-in imagegen tool on 2026-10-01 from the user's page mockups. Selected outputs are bundled here; no external image service is required by the frontend.

| File | Generation brief |
|---|---|
| hero-art.png | Isolated white indoor camera, luminous seated pose skeleton and tilted phone, wrapped in one translucent blue/mint ribbon; landscape composition. |
| hero-reference-v2.png | Transparent landing hero illustration generated on 2026-10-03 to match the supplied reference: indoor camera, phone, translucent blue/mint ribbons, and one integrated three-frame synthetic evidence card. The visible frames, labels, and times are illustrative, not live detector output. |
| signin-art.png | White indoor camera with soft blue cone of light, standing pose skeleton and tilted phone; isolated portrait composition. |
| signup-art.png | White camera over a narrow frosted panel containing a standing pose skeleton; one mint-blue ribbon; portrait composition. |
| glass-ribbon.png | Wide, lightweight translucent blue/mint glass ribbon and two glass spheres; no devices or people. |
| workflow-camera.png | Transparent synthetic white indoor camera on a pale blue disc, generated on 2026-10-03 for the capture step in the supplied workflow reference. |
| workflow-movement.png | Transparent synthetic layered blue glass frames with a cyan pose figure and play symbol, generated on 2026-10-03 for the temporal review step. No measured keypoints or real recording. |
| workflow-review.png | Transparent synthetic white avatar and pulse review tiles with a mint check, generated on 2026-10-03 for the qualified incident review step. No patient data or clinical severity claim. |
| privacy-canvas.png | Opaque pale blue-white background with soft blue edge waves and a mint base, generated on 2026-10-03 from the user's Privacy & Evidence reference. No baked text, cards, icons, buttons, footage or evidence. |

The 2026-10-01 illustrations used a shared prompt: premium clinical-glass illustration, blue-white palette (#F3F6FC), iridescent blue/teal glass, gentle studio lighting, refined white materials, complete subjects inside the frame. That prompt excluded words, numbers, logos, watermarks, buttons and interface chrome. The 2026-10-03 hero-reference-v2.png intentionally includes synthetic evidence labels and timestamps to match the supplied hero reference. Illustration assets requested genuine transparency; the demonstration room requested an opaque background.

The source mockups supplied style/composition references, not image fragments used as a functional interface. Pose coordinates and playback overlays are synthetic frontend fixtures. Artwork is not footage, detector evidence, or a performance result.

Plus Jakarta Sans is bundled from Google Fonts. Its license is preserved in OFL.txt.

The 2026-10-03 workflow artwork is decorative and uses empty alternative text because the adjacent step headings explain the process. The results-card CSS waves are decorative illustrations, not measured curves or time series. Benchmark values remain sourced from the existing frozen evaluation snapshot.

The privacy canvas uses the built-in imagegen tool with this prompt brief: reproduce only the reference's wide pale ice-blue/white canvas, very soft rounded blue waves at the edges and pale mint lower wave; leave the centre nearly white; exclude text, cards, icons, buttons, borders, watermarks, glossy 3D objects and busy glass ribbons. It is an opaque decorative CSS background; all card/CTA text and icons remain live HTML/vector components. The generated original remains preserved outside the workspace.

## Overview reference follow-up (2026-10-04)

- `overview-home.png`: opaque 2048x768 synthetic decorative home banner generated with built-in imagegen. Quiet white/ice-blue Scandinavian home, pale linen sofa and muted plant on the right; left portion remains almost empty. No people, devices, text, controls or logos. Used only as the Overview header backdrop; never displayed as a camera feed or incident evidence.
- A separate generated dashboard design reference was inspected before implementation and remains outside the source tree. The user-supplied screenshot controls composition. All headings, controls, statistics and chart labels are native UI; thumbnails come only from saved incident evidence.
- Generated originals preserved. No image fragments cropped from the supplied screenshot or generated dashboard mockup were embedded into the functional interface.
