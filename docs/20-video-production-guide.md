# 20 - Video Production Guide (end to end)

> Companion to doc 12 (Pitch Script). Doc 12 is what you say; this is how you shoot it, voice it, edit it, and publish it. Every number you are allowed to say on camera is in the Numbers Card (section 8) with its source file. Nothing else gets quoted.

## 1. Deliverable

| Item | Value |
|------|-------|
| Length | 5:00 hard cap (Razorpay expects short; judges skim) |
| Resolution | 1920x1080, 30 fps, 16:9 |
| Audio | Voice only (music optional under intro and outro, very low) |
| Format | MP4 (H.264 + AAC), uploaded to YouTube as unlisted, link pasted into the form |
| Style | Screen recording + voiceover. No slideshow, no stock footage, no intro animation beyond a 5 second title card |
| Webcam | Optional, picture-in-picture on the first and last 10 seconds only. Skip it if your camera is mediocre; screen plus voice is the standard for engineering demos |

Total production time for first-timers: one evening, about 4 hours (45 min prep, 45 min screen takes, 45 min voice, 60 to 90 min edit, 15 min publish).

## 2. The shot list (what to show, scene by scene)

Timestamps are targets. Each scene is recorded as a separate clip, so a mistake only costs that scene.

### S0. Title card (0:00 to 0:10)
- **On screen:** Black card, text only: "Abuse-Ring Sentinel" / "Cross-merchant identity-reuse fraud detection" / your name. Build this in the editor, not on screen.
- **Narration:** "UPI fraud is organized. Rings recycle the same device, the same phone, the same UPI ID across dozens of merchants, and every single merchant sees a clean first-time customer. This is a system built to see what no single merchant can."
- **Note:** No logo animation, no music swell. Boring and confident wins.

### S1. The blind spot (0:10 to 0:40)
- **On screen:** Console home (`http://localhost:3000`), the Ranked queue. Click one BLOCK_REC event so the drawer opens. Punch in on the evidence list: one device fingerprint tied to multiple customer identities across different merchants.
- **Action beats:** (1) queue scrolls, (2) drawer click, (3) slow scroll of the evidence rows so the viewer reads "same device, 6 identities, 6 merchants".
- **Narration:** "Here is a blocked event. The evidence is not one bad transaction. It is one device carrying six identities across six merchants, with a taint path to a confirmed chargeback. No merchant's own dashboard shows this, because each of them only saw their slice. That is the blind spot this system closes."

### S2. Architecture and the AI judgment call (0:40 to 1:20)
- **On screen:** System page (`/system`), the Architecture tab with the hand-drawn SVG diagram. Slow vertical scroll down the diagram, following the flow from ingest to verdict to explanation.
- **Narration:** "Every payment event hits one pipeline. Identities are extracted and linked into a graph: devices, phones, UPI IDs, with merchants as leaves, never traversed. Seven deterministic graph features score ring membership: new identity burst, taint from confirmed fraud, cross-merchant fan-out, velocity, burn-and-rotate, device-to-identity ratio, amount pattern. Out comes ALLOW, REVIEW, or a BLOCK recommendation with its evidence. One deliberate call: the LLM never scores. Scoring is deterministic and auditable. gpt-oss on AWS Bedrock does the thing it is actually good at, turning that evidence into an audit-grade explanation."

### S3. Live demo: the verdict drawer (1:20 to 2:00)
- **On screen:** Back to the queue. Open one event. Show verdict chip, feature attributions, then the LLM narrative paragraph (pre-backfilled so it appears instantly).
- **Narration:** "Each verdict carries its receipts: per-feature attribution, the linked identities, and a one paragraph explanation generated from the evidence, not from the score. An analyst can act on this in seconds and the audit trail remembers everything."

### S4. Live demo: ring replay (2:00 to 2:25)
- **On screen:** `/replay`, Ring replay page. Click Run once. Let it play in real time; the ring's scores climb as it spreads across merchants. Do not speed this up.
- **Narration:** "Now watch a ring get born. Same replay, event by event: 23, 50, 69, 82. New identity burst fires first, then taint and fan-out accumulate as the ring touches more merchants. Twelve seconds, and the ring is a BLOCK."

### S5. Live demo: attack again (2:25 to 2:50)
- **On screen:** `/playground`. Send one custom event, see the verdict. Then click "attack again reusing the device" so the second event scores dramatically higher because the graph remembers.
- **Narration:** "The graph has memory. First touch: moderate score. Attack again reusing the device: the fan-out and taint features light up and the verdict escalates. This is exactly the recycling behavior that defeats single-merchant rules."

### S6. Honest evaluation (2:50 to 3:40)
- **On screen:** `/metrics`, the Evaluation dossier. Scroll deliberately: headline metrics, confidence intervals, per-ring recall, confusion matrix, FP cost table, threshold sensitivity, then stop 5 full seconds on the evasion table with the slow-rate row visible.
- **Narration:** "Held-out test, ring-stratified so no identity leaks between splits. Precision 0.833, confidence interval 0.61 to 0.94. Recall 0.882. Both rings caught, including the sophisticated one, and zero fraud passed silently. False positives cost money, so I price them: net 38,665 rupees saved per thousand events, with the full cost model in the docs. Two disclosures I will not hide. First, a gradient boosting baseline edges my rule ensemble on F1, 0.909 versus 0.857; it is the measured argument for the hybrid, and it is printed right there. Second, slow-rate evasion rings get through the current weights, 90 percent of them; that is documented with the fix, not silently patched."
- **Note:** This is the scene judges rewatch. Do not rush it. Let the evasion table sit on screen.

### S7. Engineering proof (3:40 to 4:05)
- **On screen:** Split view: terminal on the left, GitHub Actions page on the right (`github.com/Prakhar2025/Sentinel/actions`, latest run, all 4 jobs green).
- **Terminal actions:** run `make check` (202 tests, ruff, mypy strict), then `make evaluate` followed by `sha256sum evaluation/metrics.json` twice to show the byte-identical hash. Speed the terminal clips up 4x with a small "4x" caption; keep the final hash line at 1x.
- **Narration:** "Reproducibility is enforced, not promised. Seed 42, one command, byte-identical metrics twice. Two hundred two tests, strict type checks, and CI runs quality, container, Postgres, and secret-scan jobs on every push. The challenger shadow model runs beside the champion, agrees with it 96 percent of the time, and has written promotion criteria it must meet."

### S8. What broke (4:05 to 4:35)
- **On screen:** `docs/what-broke.md` open (GitHub or editor, dark theme). Scroll past three entries, 5 seconds each: the F6 weight-32 calibration shortcut, the all-fraud-in-train split bug, the merchant-traversal cluster flood.
- **Narration:** "Thirty-plus entries in the what-broke log, because real builds break. My first calibration inflated the amount feature to weight 32 by exploiting my own synthetic data. My first split put every fraud event in train, silently making the test set useless, so now a unit test proves fraud reaches every split. And the graph once crawled through merchants, flooding every cluster; merchants are leaves now and cluster extraction dropped from 15 seconds to under a millisecond."
- **Note:** Do not read from the file on camera. Glance, speak, move on.

### S9. Roadmap and close (4:35 to 5:00)
- **On screen:** System page roadmap tab or doc 11 scrolled once, then a plain end card: "Abuse-Ring Sentinel" + repo link + article link.
- **Narration:** "Next: a GNN on the same feature schema when real labeled data exists, and federated verdict sharing so merchants get the network signal without sharing customer data. The system is defense-only by construction: it recommends, humans decide. Code, docs, and the full evaluation are in the repo. Thank you."

If you must cut for time: trim S1 or drop S5. Never cut S6 or S8; they carry the honesty signal that separates this from template submissions.

## 3. Pre-flight setup (do once, 45 minutes)

### Machine
- Laptop plugged in, power mode Best performance, screen sleep Off, night light Off (colors must be true).
- Windows display scale 100 percent (Settings > Display) so the recording is crisp.
- Do Not Disturb ON; close Slack, WhatsApp, mail, every notification source.
- Pause OneDrive for the session (taskbar icon > Pause). It has caused silent file races in this project before; do not let it pop mid-take.

### Windows
- Hide taskbar (right-click taskbar > Taskbar settings > Automatically hide) and remove Widgets and Chat.
- Optional but clean: hide desktop icons (right-click desktop > View > uncheck Show desktop icons).

### Browser
- `Ctrl+Shift+B` to hide the bookmarks bar. Zoom 100 percent. Dark theme.
- Open tabs in this exact order: `localhost:3000` (console), `/replay`, `/playground`, `/metrics`, `/system`, GitHub Actions page, `docs/what-broke.md` on GitHub.

### Terminal
- Windows Terminal with a Git Bash profile, Cascadia Code, font size 16 to 18, window snapped to the right half (`Win+Right`). Browser snapped left (`Win+Left`).

### Demo state (exact sequence, from a clean start)
```bash
cd ~/OneDrive/Desktop/Razorpay
rm -f sentinel.db*
make serve        # terminal 1, leave running
make backfill     # terminal 2, fills LLM narratives (bounded, uses Bedrock)
# restart make serve in terminal 1 for the fresh-replay experience
make console      # terminal 3, Next.js on :3000
```
- If you plan to show a live explanation call, make one warm-up call first so the first on-camera call is not the cold one. The explain endpoint is capped at 50 calls per day.

## 4. Recording setup

### OBS Studio (free, obsproject.com)
1. Install, run the auto-wizard, choose "Optimize just for recording".
2. Settings > Video: Base 1920x1080, Output 1920x1080, FPS 30.
3. Settings > Output > Recording: Format MKV (crash-safe), Encoder x264, Rate control CRF, CRF 18. Remux to MP4 after recording (File > Remux Recordings).
4. Settings > Audio: Sample rate 48 kHz. Mute Desktop Audio so notification pings never reach the track.
5. Add a Display Capture source (full screen) and an Audio Input Capture source for your mic.
6. Mic filters, in order: Noise Suppression (RNNoise), Gain to taste, Limiter at -6 dB.

### Audio rules
- Any mic works if you follow distance: 10 to 15 cm from your mouth, slightly off-axis (avoids pops). Earbud mics are acceptable; a phone on a stand recording separately is better than a laptop mic.
- Target level: peaks between -12 and -6 dB, never touching 0.
- Room: curtains or a blanket behind you, fan and AC off for the takes.
- Record 30 seconds of test, play it back on headphones, fix hum or echo before doing real takes. This 5 minutes saves a re-record.

### Two-pass recording (recommended)
- **Pass 1, silent screen:** record each scene's clicks and scrolls per the shot list. No narration, no pressure. One file per scene.
- **Pass 2, voice:** record narration per scene (OBS with mic only, or Audacity). Per-scene voice means a flub costs one sentence, not the video.
- Single-take live narration is the fallback if you are short on time, but expect more resets.

## 5. Voice and delivery

- Read aloud once before recording; the script is written for the ear, at about 150 words per minute.
- Mark the emphasis words (in doc 12, italicized terms are the ones to hit): "same device", "never scores", "byte-identical", "disclosed".
- If you flub a word: pause 2 full seconds, repeat the whole sentence, keep rolling. The pause is your cut point.
- Smile on the first and last line; it audibly changes tone. Sit upright; slumping compresses your voice.
- Keep room-temperature water nearby. Record standing if it helps energy.

## 6. Editing (CapCut desktop, free; DaVinci Resolve if you outgrow it)

Cut list, in order:
1. Import all scene clips, drop them on the timeline in shot-list order.
2. Trim dead air at both ends of every clip; cut the 2-second flub pauses.
3. Speed up the terminal scene 4x (add a "4x" caption). Leave the ring replay at 1x; it is the payoff.
4. Punch-in zooms (keyframe scale 100 to 130 percent) on: the evidence rows (S1), the verdict chip (S3), the score climb (S4), the CI and evasion rows (S6), the sha256 match (S7). One zoom per scene, maximum.
5. Auto captions in CapCut, then proofread every card. Fix "gpt-oss", "UPI", "VPA", rupee symbol, "Bedrock". Bad captions read as slop faster than any visual.
6. Optional music: YouTube Audio Library only (copyright-safe), under S0 and S9 at -20 dB. Voice-only is completely fine and arguably more credible.
7. Export: 1080p, 30 fps, H.264, bitrate 12 Mbps or "High", AAC audio.

## 7. Thumbnail

YouTube wants 1280x720. The submission cover already exists at 1200x675 (`docs/assets/cover.svg`). For the thumbnail: open the SVG in Chrome, `Win+Shift+S` a full-window snip, or render at any size and let YouTube letterbox. Text on the thumbnail: "Fraud rings recycle identities. This system sees them." plus the project name. No gradients on gradients, no fake screenshots.

## 8. The Numbers Card (say nothing that is not here)

| Number | Exact value | Source | Where it appears |
|--------|-------------|--------|------------------|
| Precision | 0.833, CI 0.61 to 0.94 | `evaluation/metrics.json` `precision_ci95` | S6 |
| Recall | 0.882, CI 0.66 to 0.97 | `evaluation/metrics.json` `recall_ci95` | S6 |
| F1 (ensemble) | 0.857 | `event_metrics.f1` | S6 |
| GBDT baseline F1 | 0.909 | `baselines.gradient_boosting.f1` | S6 |
| Rings caught | 2 of 2; sophisticated ring 8 of 9 events flagged | `ring_recall` | S6 |
| Fraud silently allowed | 0 (ALLOW: 113 clean, 0 fraud) | `confusion` | S6 |
| Net saved | Rs 38,665 per 1,000 events | `fp_cost_per_1000.net_saved_inr` | S6 |
| Thresholds | review 42, block 49 | `thresholds` | S6 dossier |
| Slow-rate evasion | 90 percent missed (18 of 20), disclosed | `evasion_pack.strategies.slow_rate` | S6 |
| Shadow agreement | 96.45 percent on 197 events | `champion_challenger.agreement_rate` | S7 |
| Throughput | 178 events per second, p50 4.8 ms, p95 15.2 ms | `evaluation/loadtest.json` | S7 (optional) |
| Tests | 202 passing, mypy strict clean | `make check` | S7 |
| Reproducibility | seed 42, byte-identical metrics hash twice | `make evaluate` + `sha256sum` | S7 |
| Cluster extraction | 15 s to under 1 ms after merchant-leaf fix | `docs/what-broke.md` | S8 |

Rules: quote CI numbers from this card only, never from memory. If a number is not in this table, it does not go in the video.

## 9. Contingencies

- **Bedrock explanation is slow on camera:** use the backfilled narratives for S3; show a live call only if warmed. Never record a 10 second silent stare; cut it.
- **Demo state degrades mid-session:** `rm -f sentinel.db*`, re-serve, re-backfill, restart serve, re-record only the affected scene. Modular recording is your insurance.
- **OBS or Windows crashes:** you recorded to MKV, so nothing is lost; remux and continue.
- **Mic quality unacceptable:** record voice on your phone (voice memo app, 15 to 20 cm, airplane mode on), then sync with a single clap at scene start.
- **Over 5:00 after editing:** cut S5, then tighten S1. Never touch S6 or S8.

## 10. Publish and submit

1. Export the MP4, back it up to OneDrive.
2. YouTube upload, visibility **Unlisted**.
   - Title: "Abuse-Ring Sentinel: cross-merchant UPI fraud-ring detection (buildathon build)"
   - Chapters: `0:00 The blind spot` / `0:40 How it works` / `1:20 Live demo` / `2:50 Honest evaluation` / `3:40 Engineering proof` / `4:05 What broke` / `4:35 What's next`
   - Description: two lines on the problem, repo link, deep-dive article link, "defense-only: it recommends, humans decide".
3. Thumbnail: render of the cover with the one-liner (section 7).
4. Submission form: paste the video link, the public repo link, Working Professional, and the short story below.
5. Only make the repo public after a final check that `DEPLOY-PRIVATE.md` and `.env` are still gitignored (`git status --short` shows no untracked secret files, `git ls-files | grep -i "deploy-private\|^\.env$"` returns nothing).

Short story for the form (fits the 300 character limit):

> Fraud rings recycle the same devices, phones, and VPAs across merchants; each merchant sees a clean first-timer. Sentinel links identities into one cross-merchant graph and scores rings deterministically, with evidence. The LLM never scores; it explains. Honest metrics, evasion disclosed.

## 11. Time budget

| Block | Time |
|-------|------|
| Pre-flight and demo state | 45 min |
| Screen takes (9 scenes, 2 takes each worst case) | 45 min |
| Voice takes per scene | 45 min |
| Edit, captions, export | 60 to 90 min |
| Publish and form | 15 min |
| **Total** | **about 4 hours, one evening** |
