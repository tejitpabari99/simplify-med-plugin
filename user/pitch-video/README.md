# 60-second pitch video

`simplify-med-pitch.mp4` (1920×1080, 30 fps, 60 s, with soundtrack) is a
kinetic-typography pitch built from `user/research-report.md`, the `simplify`
skill and the `prep` / `med-lit` direction on `users/tejitpabari/add-med-skills`.

| Time | Scene |
|---|---|
| 0–6 s | Hook: patient quote, then “200+ surveyed · 50 patient interviews · 30 clinician interviews” |
| 6–11 s | Research scale counters |
| 11–21 s | Patient pain: 57% / 51% / 76% / 78% (53% distrust search) waffles + patient quotes |
| 21–28 s | Clinician side: “A thousand pages…”, 95% want concise info, barrier bars |
| 28–39 s | simplify·med reveal; jargon → source-cited care plan; AHRQ word swaps |
| 39–46 s | Grounding pipeline and the three guarantees |
| 46–52 s | simplify (live), prep and med-lit (next), with research support |
| 52–57 s | Distribution through ChatGPT; Epic and health-system record connections |
| 57–60 s | Vision: longitudinal, structured understanding; end card |

Headline participant counts are the rounded fieldwork totals. The percentages
come from the connected, de-identified corpus in `user/data/metrics.csv` and
`user/data/current_skill_support.csv`. The discharge excerpt is from the
synthetic test fixture.

## Re-render

Requires Node with Playwright (Chromium), Python 3 with `numpy` and
`imageio-ffmpeg`. Set `FF` in `render.mjs` to your ffmpeg path.

```bash
cd user/pitch-video
python3 audio.py          # writes music.wav
node render.mjs           # writes simplify-med-pitch.mp4
```

Open `pitch.html?t=12.5` in a browser to preview any moment.
