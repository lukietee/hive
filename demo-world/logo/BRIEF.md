# Logo brief: the rough sketch (🎨 Design agent finishes it)

## Draw this in Procreate BEFORE the demo (it's part of the "mess")
- **Canvas:** square, 2048×2048, cream background (#F6F1E7)
- **Layer name:** `sketch` (the agent hides this layer at the end, so the name matters)
- **Brush:** any pencil (6B or Technical Pencil), dark grey, ~3 minutes, intentionally rough:
  1. A wide **bowl** shape (a half-circle, flat top), center of the canvas
  2. A **whisk swirl** rising out of the bowl: 2–3 loose arcs
  3. A small **leaf** on one side (optional)
  4. No text. Don't write "Whisk"; image models garble letters.
- Leave it messy: wobbly lines, a couple of overlapping strokes. The before/after should be obvious.

## Gemini prompt (Design agent → Gemini image model)
```
Turn this rough sketch into a clean, modern, flat vector-style app logo.
Keep the same composition: a matcha bowl with a whisk swirl rising out of it.
Palette: deep green #2F5D3A, matcha green #8DBF5A, cream #F6F1E7.
Simple geometric shapes, bold even strokes, centered, generous padding,
plain cream background, no text, no letters, no gradients, no shadows.
```

## Output handling
- Save as `logo.png` (1024×1024), handed to:
  - 🔵 Web → `site/logo.png` (the `<img id="logo">` in the nav)
  - 🟡 Deck → `s1_img_slot` and `s3_img_slot` in `pitch.pptx`
  - 🟣 Social → attached to the launch post
- Then AirDropped to the iPad → inserted into Procreate as a new layer above `sketch` → `sketch` layer hidden.

## Fallbacks
- **Cache:** generate 3–5 results in advance from the real sketch and keep the best as `logo_cached.png`. Use it if Gemini is slow on venue Wi-Fi.
- **Last resort:** `../site/FINISHED/logo.svg` (a hand-made placeholder mark).
