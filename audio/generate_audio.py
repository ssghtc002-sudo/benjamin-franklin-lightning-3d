"""
Scientist #10: Benjamin Franklin (1752) — Catching Lightning With a Kite
V10 Viral Cinema Broadcast-Mastered Studio Audio (AGENTS.md Standard):
  - Studio Microsoft Neural Voices (edge-tts):
      * Narrator: en-US-BrianNeural (warm viral documentary anchor)
      * Benjamin Franklin: en-US-AndrewNeural (charismatic 18th-century polymath)
      * William Franklin: en-US-SteffanNeural (energetic younger son)
  - 120 BPM Storm-Tension Baroque Harpsichord + Low Cello Ostinato + Electric-Age Brass/Synth Swell
  - Living Stormy Meadow Ambience Bed (gentle rain sheen + wind -> starry electric-night hum)
  - Spatial High-Voltage Foley SFX (thunderbolt kite strike, brass key ting, knuckle spark SNAP,
    Leyden jar plasma charge, copper lightning rod intercept & grounding drain, modern grid ignition)
  - Vocal-Pocket EQ (250-3500 Hz) + -9.5 dB Sidechain Ducking + ITU-R BS.1770-4 (-14.0 LUFS, TP <= -1.5 dBFS)
  - Exact 48,000 Hz Stereo (1,440,000 samples = 30.000s), 30 Hz Dual-Axis Lip-Sync & Boxless ASS/SRT
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TIMELINE_PATH = PROJECT_ROOT / "config" / "timeline.json"

SR = 48000
CHANNELS = 2
DURATION = 30.0
TOTAL_SAMPLES = int(round(DURATION * SR))  # 1,440,000 exact samples
LIP_FPS = 30
LIP_TOTAL_FRAMES = int(round(DURATION * LIP_FPS))  # 900 exact samples @ 30 Hz

TARGET_LUFS = -14.0
TRUE_PEAK_CEILING_DBFS = -1.62
TRUE_PEAK_CEILING_LIN = 10.0 ** (TRUE_PEAK_CEILING_DBFS / 20.0)
AMBIENCE_TARGET_DBFS = -37.0

BPM = 120.0
BEAT = 60.0 / BPM

EDGE_NEURAL_VOICES: dict[str, dict[str, Any]] = {
    "narrator": {"voice": "en-US-BrianNeural", "pitch": "-1Hz", "pan": 0.0},
    "franklin": {"voice": "en-US-AndrewNeural", "pitch": "-2Hz", "pan": -0.18},
    "william": {"voice": "en-US-SteffanNeural", "pitch": "+2Hz", "pan": 0.20},
}

# Natural comma-phrased TTS overrides (display captions stay verbatim from timeline.json)
TTS_OVERRIDES: dict[str, str] = {
    "L1": "In 1752, one wild man flew a kite into a storm, to catch lightning on a key!",
    "L2": "Father, stop, that lightning bolt could kill us!",
    "L3": "Touch the brass key, William, lightning is pure electricity!",
    "L4": "He bottled real storm lightning in a glass Leyden jar, naming positive and negative charge!",
    "L5": "Then Franklin built the copper lightning rod,",
    "L6": "Whoa, it steered a thunderbolt straight into the earth!",
    "L7": "One fearless storm test saved millions of homes, and sparked the entire electric age!",
    "L8": "Skyscrapers, batteries, your phone right now, all trace back to Benjamin Franklin!",
}


# ============================================================================
# CORE DSP UTILITIES (48 kHz)
# ============================================================================
def midi_to_hz(midi: float) -> float:
    return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))


def pan_stereo(mono: np.ndarray, pan: float) -> np.ndarray:
    pan = float(np.clip(pan, -1.0, 1.0))
    angle = (pan + 1.0) * (math.pi / 4.0)
    return np.stack([mono * math.cos(angle), mono * math.sin(angle)], axis=-1).astype(np.float32)


def pan_sweep_stereo(mono: np.ndarray, pan_start: float, pan_end: float) -> np.ndarray:
    n = len(mono)
    p = np.linspace(float(np.clip(pan_start, -1.0, 1.0)), float(np.clip(pan_end, -1.0, 1.0)), n, dtype=np.float32)
    ang = (p + 1.0) * (math.pi / 4.0)
    return np.stack([mono * np.cos(ang), mono * np.sin(ang)], axis=-1).astype(np.float32)


def add_stereo_event(bus: np.ndarray, event: np.ndarray, start_time: float) -> None:
    if event.ndim == 1:
        event = pan_stereo(event, 0.0)
    idx = int(round(start_time * SR))
    if idx >= len(bus) or idx + len(event) <= 0:
        return
    src_start = max(0, -idx)
    dst_start = max(0, idx)
    copy_len = min(len(event) - src_start, len(bus) - dst_start)
    if copy_len > 0:
        bus[dst_start : dst_start + copy_len] += event[src_start : src_start + copy_len]


def butter_filter(audio: np.ndarray, btype: str, cutoff: float | tuple[float, float], order: int = 2) -> np.ndarray:
    nyq = 0.5 * SR
    if isinstance(cutoff, tuple):
        wn = [float(np.clip(c / nyq, 1e-4, 0.999)) for c in cutoff]
    else:
        wn = float(np.clip(cutoff / nyq, 1e-4, 0.999))
    sos = signal.butter(order, wn, btype=btype, output="sos")
    return signal.sosfilt(sos, audio, axis=0).astype(np.float32)


def peaking_eq(mono: np.ndarray, freq: float, q: float, gain_db: float) -> np.ndarray:
    a_lin = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * freq / SR
    alpha = math.sin(w0) / (2.0 * q)
    cos_w0 = math.cos(w0)
    b0 = 1.0 + alpha * a_lin
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * a_lin
    a0 = 1.0 + alpha / a_lin
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / a_lin
    b = np.array([b0, b1, b2], dtype=np.float64) / a0
    a = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)
    return signal.lfilter(b, a, mono.astype(np.float64), axis=0).astype(np.float32)


def smooth_envelope(sig: np.ndarray, attack_ms: float, release_ms: float) -> np.ndarray:
    x = np.abs(sig).astype(np.float32)
    if x.ndim == 2:
        x = np.max(x, axis=1)
    att = math.exp(-1.0 / max(1.0, (attack_ms * 0.001) * SR))
    rel = math.exp(-1.0 / max(1.0, (release_ms * 0.001) * SR))
    step = 64
    n_blk = (len(x) + step - 1) // step
    blk_max = np.zeros(n_blk, dtype=np.float32)
    for i in range(n_blk):
        blk_max[i] = float(np.max(x[i * step : min(len(x), (i + 1) * step)]))
    att_b = att ** step
    rel_b = rel ** step
    env_b = np.zeros(n_blk, dtype=np.float32)
    cur = 0.0
    for i in range(n_blk):
        v = float(blk_max[i])
        cur = (att_b * cur + (1.0 - att_b) * v) if v > cur else (rel_b * cur + (1.0 - rel_b) * v)
        env_b[i] = cur
    idx = np.linspace(0, n_blk - 1, len(x), dtype=np.float32)
    return np.interp(idx, np.arange(n_blk, dtype=np.float32), env_b).astype(np.float32)


def add_outdoor_reverb(stereo: np.ndarray, mix: float = 0.08) -> np.ndarray:
    taps = [(0.017, 0.34, -0.35), (0.029, 0.25, 0.32), (0.047, 0.16, -0.18), (0.073, 0.10, 0.24)]
    wet = np.zeros_like(stereo)
    mono = 0.5 * (stereo[:, 0] + stereo[:, 1])
    for delay_s, g, p in taps:
        d = int(round(delay_s * SR))
        if d < len(mono):
            shifted = np.zeros_like(mono)
            shifted[d:] = mono[:-d] * g
            wet += pan_stereo(shifted, p)
    wet = butter_filter(wet, "low", 4600.0, order=2)
    return ((1.0 - mix) * stereo + mix * wet).astype(np.float32)


def trim_silence(mono: np.ndarray, sr: int = SR, thresh_db: float = -42.0) -> tuple[np.ndarray, float]:
    peak = float(np.max(np.abs(mono)) + 1e-12)
    thr = peak * (10.0 ** (thresh_db / 20.0))
    idx = np.where(np.abs(mono) > thr)[0]
    if len(idx) == 0:
        return mono, 0.0
    pad_l = int(0.012 * sr)
    pad_r = int(0.022 * sr)
    i0 = max(0, int(idx[0]) - pad_l)
    i1 = min(len(mono), int(idx[-1]) + pad_r)
    return mono[i0:i1].astype(np.float32), i0 / float(sr)


def broadcast_vocal_chain(mono: np.ndarray) -> np.ndarray:
    y = butter_filter(mono, "high", 85.0, order=2)
    y = peaking_eq(y, 260.0, 1.3, -1.6)
    y = peaking_eq(y, 3400.0, 1.0, +2.4)
    y = peaking_eq(y, 6800.0, 0.9, +1.5)
    env = smooth_envelope(y, attack_ms=6.0, release_ms=95.0)
    thr = 0.14
    ratio = 3.0
    gain = np.ones_like(env)
    over = env > thr
    gain[over] = (thr + (env[over] - thr) / ratio) / np.maximum(env[over], 1e-6)
    y = (y * gain).astype(np.float32)
    rms = float(np.sqrt(np.mean(y ** 2) + 1e-12))
    y = y * (0.20 / max(1e-5, rms))
    return np.tanh(y * 0.95).astype(np.float32)


def ffmpeg_atempo_48k(mono: np.ndarray, rate: float) -> np.ndarray:
    if abs(rate - 1.0) < 0.008:
        return mono.astype(np.float32)
    rate = float(np.clip(rate, 0.85, 1.22))
    with tempfile.TemporaryDirectory() as td:
        in_p = Path(td) / "in.wav"
        out_p = Path(td) / "out.wav"
        sf.write(str(in_p), mono.astype(np.float32), SR, subtype="FLOAT")
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(in_p), "-filter:a", f"atempo={rate:.4f}", "-ar", str(SR), "-ac", "1", str(out_p), "-loglevel", "error"],
            check=True,
        )
        y, _ = sf.read(str(out_p), dtype="float32")
    return y.astype(np.float32)


async def _edge_tts_synth_async(text: str, voice: str, rate_pct: int, pitch: str) -> tuple[np.ndarray, list[dict[str, Any]]]:
    import edge_tts

    rate_str = f"{rate_pct:+d}%"
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate_str, pitch=pitch)
    mp3_bytes = bytearray()
    word_marks: list[dict[str, Any]] = []
    async for chunk in comm.stream():
        ctype = chunk.get("type")
        if ctype == "audio":
            mp3_bytes.extend(chunk["data"])
        elif ctype == "WordBoundary":
            t0 = float(chunk["offset"]) / 1e7
            dur = float(chunk["duration"]) / 1e7
            word_marks.append({"text": str(chunk["text"]), "start": t0, "end": t0 + dur})

    with tempfile.TemporaryDirectory() as td:
        mp3_p = Path(td) / "voice.mp3"
        wav_p = Path(td) / "voice.wav"
        mp3_p.write_bytes(bytes(mp3_bytes))
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_p), "-ar", str(SR), "-ac", "1", str(wav_p), "-loglevel", "error"],
            check=True,
        )
        y, _ = sf.read(str(wav_p), dtype="float32")
    return y.astype(np.float32), word_marks


def tokenize_display_words(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in text.strip().split():
        if "—" in raw and not raw.endswith("—"):
            parts = raw.split("—")
            for idx, part in enumerate(parts):
                if idx < len(parts) - 1:
                    tokens.append(part + "—")
                elif part:
                    tokens.append(part)
        else:
            tokens.append(raw)
    return [t for t in tokens if t]


def align_words_to_audio(words: list[str], audio: np.ndarray, t0: float, t1: float) -> list[dict[str, Any]]:
    if not words:
        return []
    weights = np.array(
        [
            max(1.8, float(len(re.sub(r"[^A-Za-z0-9]", "", w))))
            + (1.6 if w.endswith(("!", "?", ".")) else (1.1 if w.endswith(("—", ",", ";", ":")) else 0.0))
            for w in words
        ],
        dtype=np.float64,
    )
    weights /= weights.sum()
    dur = max(0.05, t1 - t0)
    bounds = [t0]
    acc = 0.0
    for wt in weights[:-1]:
        acc += float(wt)
        bounds.append(t0 + dur * acc)
    bounds.append(t1)
    out = [{"word": w, "start": round(bounds[i], 4), "end": round(bounds[i + 1], 4)} for i, w in enumerate(words)]
    out[-1]["end"] = round(t1, 4)
    return out


def compute_lip_sync(
    speaker_mono_buses: dict[str, np.ndarray], fps: int = LIP_FPS, total_frames: int = LIP_TOTAL_FRAMES
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    lip_map: dict[str, list[float]] = {}
    narrow_map: dict[str, list[float]] = {}
    hop = int(round(SR / fps))
    win = int(round(SR / 18))
    for spk, bus in speaker_mono_buses.items():
        has_sig = bool(np.any(bus))
        low_bus = butter_filter(bus, "band", (220.0, 820.0), order=2) if has_sig else bus
        hi_bus = butter_filter(bus, "band", (1100.0, 3400.0), order=2) if has_sig else bus
        vals = np.zeros(total_frames, dtype=np.float32)
        nvals = np.zeros(total_frames, dtype=np.float32)
        for f in range(total_frames):
            c = min(len(bus) - 1, f * hop + hop // 2)
            lo, hi = max(0, c - win // 2), min(len(bus), c + win // 2)
            seg = bus[lo:hi]
            rms = float(np.sqrt(np.mean(seg ** 2) + 1e-12)) if len(seg) > 0 else 0.0
            if rms > 0.012:
                vals[f] = rms
                e_lo = float(np.sqrt(np.mean(low_bus[lo:hi] ** 2) + 1e-12))
                e_hi = float(np.sqrt(np.mean(hi_bus[lo:hi] ** 2) + 1e-12))
                nvals[f] = float(np.clip((e_lo / (e_lo + e_hi + 1e-6) - 0.40) * 2.35, 0.0, 1.0))

        active = vals > 0.012
        p92 = float(np.percentile(vals[active], 92)) if np.any(active) else 0.1
        normed = np.clip(vals / max(0.04, p92), 0.0, 1.0)
        n_gated = np.clip(nvals * np.minimum(1.0, normed * 1.45), 0.0, 1.0)
        sm, nsm = np.copy(normed), np.copy(n_gated)
        for i in range(1, total_frames):
            a_lip = 0.65 if normed[i] > sm[i - 1] else 0.52
            sm[i] = (1.0 - a_lip) * sm[i - 1] + a_lip * normed[i]
            a_nar = 0.56 if n_gated[i] > nsm[i - 1] else 0.46
            nsm[i] = (1.0 - a_nar) * nsm[i - 1] + a_nar * n_gated[i]
        sm[sm < 0.008] = 0.0
        nsm[nsm < 0.008] = 0.0
        lip_map[spk] = [round(float(v), 4) for v in np.clip(sm, 0.0, 1.0)]
        narrow_map[spk] = [round(float(v), 4) for v in np.clip(nsm, 0.0, 1.0)]
    return lip_map, narrow_map


def synthesize_dialogue(
    timeline: dict[str, Any],
) -> tuple[np.ndarray, dict[str, np.ndarray], list[dict[str, Any]]]:
    speakers_cfg = timeline["speakers"]
    narrator_bus = np.zeros((TOTAL_SAMPLES, CHANNELS), dtype=np.float32)
    scene_voice_bus = np.zeros((TOTAL_SAMPLES, CHANNELS), dtype=np.float32)
    speaker_mono_buses = {spk: np.zeros(TOTAL_SAMPLES, dtype=np.float32) for spk in speakers_cfg}
    manifest_lines: list[dict[str, Any]] = []

    for item in timeline["dialogue"]:
        lid = item["id"]
        spk = item["speaker"]
        cfg = EDGE_NEURAL_VOICES.get(spk, EDGE_NEURAL_VOICES["narrator"])
        slot_start, slot_end = float(item["start"]), float(item["end"])
        slot_dur = slot_end - slot_start
        tts_text = TTS_OVERRIDES.get(lid, item["text"].replace("—", ", "))

        # Pass 1: 1.00x natural studio neural cadence
        rate_pct = 0
        raw_wav, _ = asyncio.run(_edge_tts_synth_async(tts_text, cfg["voice"], rate_pct, cfg["pitch"]))
        comp, _ = trim_silence(raw_wav, SR)
        comp_dur = len(comp) / float(SR)

        # Pass 2: Gentle neural rate step-up if longer than beat window (zero word slicing!)
        if comp_dur > slot_dur * 0.96:
            rate_pct = max(4, min(22, int(math.ceil((comp_dur / (slot_dur * 0.93) - 1.0) * 100.0))))
            raw2, _ = asyncio.run(_edge_tts_synth_async(tts_text, cfg["voice"], rate_pct, cfg["pitch"]))
            comp2, _ = trim_silence(raw2, SR)
            if len(comp2) < len(comp):
                comp = comp2
                comp_dur = len(comp) / float(SR)

        # Pass 3: Adaptive gentle atempo if still marginally over slot (NEVER slice off trailing syllables!)
        atempo = 1.0
        if comp_dur > slot_dur * 0.97:
            atempo = float(np.clip(comp_dur / (slot_dur * 0.95), 1.0, 1.16))
        fitted = ffmpeg_atempo_48k(comp, atempo)
        processed = broadcast_vocal_chain(fitted)

        actual_dur = len(processed) / float(SR)
        t0 = slot_start
        t1 = min(DURATION - 0.04, t0 + actual_dur)
        max_len = int(round((t1 - t0) * SR))
        if len(processed) > max_len:
            # Gentle tail fade only if hitting 30.000s end boundary
            processed = processed[:max_len]
        fade_n = min(int(0.014 * SR), len(processed) // 4)
        if fade_n > 0:
            processed[:fade_n] *= np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
            processed[-fade_n:] *= np.linspace(1.0, 0.0, fade_n, dtype=np.float32)

        idx0 = int(round(t0 * SR))
        speaker_mono_buses[spk][idx0 : idx0 + len(processed)] += processed
        st = pan_stereo(processed, float(cfg["pan"]))
        if spk == "narrator":
            add_stereo_event(narrator_bus, st, t0)
        else:
            add_stereo_event(scene_voice_bus, st, t0)

        disp_words = tokenize_display_words(item["text"])
        aligned = align_words_to_audio(disp_words, processed, t0, t1)
        manifest_lines.append(
            {
                "id": lid,
                "beatId": item["beatId"],
                "speaker": spk,
                "text": item["text"],
                "start": round(t0, 4),
                "end": round(t1, 4),
                "words": aligned,
            }
        )
        print(
            f"  [EdgeTTS] {lid} ({spk:8s} | {cfg['voice']} rate={rate_pct:+d}% atempo={atempo:.2f}x): "
            f"{t0:5.2f}s..{t1:5.2f}s (dur={t1-t0:.2f}s / slot={slot_dur:.2f}s)"
        )

    dialogue_bus = narrator_bus + add_outdoor_reverb(scene_voice_bus, mix=0.08)
    return dialogue_bus, speaker_mono_buses, manifest_lines


# ============================================================================
# 120 BPM STORM-TENSION BAROQUE & ELECTRIC CINEMA SCORE
# ============================================================================
def synth_cello_note(midi: float, dur: float, amp: float = 0.25) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    f = midi_to_hz(midi)
    vib = 1.0 + 0.004 * np.sin(2.0 * math.pi * 5.2 * t)
    ph = 2.0 * math.pi * np.cumsum(f * vib) / SR
    sig = 0.55 * np.sin(ph) + 0.26 * np.sin(2.0 * ph) + 0.14 * np.sin(3.0 * ph) + 0.05 * np.sin(4.0 * ph)
    env = np.minimum(1.0, t / 0.06) * np.minimum(1.0, (dur - t) / 0.08)
    return (butter_filter(sig, "low", 1400.0, order=2) * env * amp).astype(np.float32)


def synth_harpsichord_pluck(midi: float, dur: float, amp: float = 0.16) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    f = midi_to_hz(midi)
    sig = (
        0.48 * np.sin(2.0 * math.pi * f * t)
        + 0.30 * np.sin(4.0 * math.pi * f * t) * np.exp(-t * 3.5)
        + 0.16 * np.sin(6.0 * math.pi * f * t) * np.exp(-t * 5.5)
        + 0.08 * np.sin(8.0 * math.pi * f * t) * np.exp(-t * 8.0)
    )
    env = np.minimum(1.0, t / 0.005) * np.exp(-t * 3.2)
    return (sig * env * amp).astype(np.float32)


def compose_franklin_score() -> np.ndarray:
    bus = np.zeros((TOTAL_SAMPLES, CHANNELS), dtype=np.float32)
    # 120 BPM C Minor storm tension -> Eb Major discovery -> C Major electric triumph!
    chords = [
        (0.0, 4.5, [36, 48, 55, 63]),   # Cm Storm Hook
        (4.5, 9.8, [41, 53, 60, 68]),   # Fm Tension Debate
        (9.8, 15.5, [39, 51, 58, 67]),  # Eb Major Leyden Wonder
        (15.5, 20.5, [43, 55, 62, 67]), # G Dominant Storm Climax
        (20.5, 25.5, [44, 56, 63, 72]), # Ab -> Electric Rise
        (25.5, 30.0, [48, 60, 64, 72]), # C Major Monument Finale
    ]
    for t0, t1, notes in chords:
        dur = t1 - t0
        # Deep cello bass + warm pad
        add_stereo_event(bus, pan_stereo(synth_cello_note(notes[0], dur, 0.24), -0.15), t0)
        add_stereo_event(bus, pan_stereo(synth_cello_note(notes[1], dur, 0.16), 0.18), t0)
        # Driving 8th-note baroque harpsichord & modern electric pulse
        step_t = t0
        k = 0
        while step_t < t1 - 0.12:
            m = notes[1 + (k % (len(notes) - 1))] + (12 if (k % 4 == 3) else 0)
            p = -0.32 if (k % 2 == 0) else 0.32
            add_stereo_event(bus, pan_stereo(synth_harpsichord_pluck(m, 0.36, 0.12), p), step_t)
            # Subtle cinematic timpani pulse on downbeats
            if k % 4 == 0:
                tn = int(0.32 * SR)
                tt = np.arange(tn, dtype=np.float32) / SR
                f0 = midi_to_hz(notes[0]) * (1.0 + 0.35 * np.exp(-tt * 28.0))
                drum = np.sin(2.0 * math.pi * np.cumsum(f0) / SR) * np.exp(-tt * 9.5) * 0.22
                add_stereo_event(bus, pan_stereo(drum, 0.0), step_t)
            step_t += BEAT * 0.5
            k += 1

    # Rising electric harmonic shimmer from Beat 5 into Finale
    n_fin = int(9.5 * SR)
    tf = np.arange(n_fin, dtype=np.float32) / SR
    shimmer = (
        0.09 * np.sin(2.0 * math.pi * midi_to_hz(72) * tf)
        + 0.06 * np.sin(2.0 * math.pi * midi_to_hz(79) * tf)
    ) * np.minimum(1.0, tf / 2.2) * np.minimum(1.0, (9.5 - tf) / 1.0)
    add_stereo_event(bus, pan_stereo(shimmer.astype(np.float32), 0.0), 20.5)

    # Vocal-pocket EQ cut (250-3500 Hz) per AGENTS.md so Edge-TTS stays razor-clear
    bus = add_outdoor_reverb(bus, mix=0.14)
    for ch in range(CHANNELS):
        bus[:, ch] = peaking_eq(bus[:, ch], 1150.0, 0.65, -4.2)
    return (bus * 0.42).astype(np.float32)


def compose_storm_ambience_bed() -> np.ndarray:
    rng = np.random.default_rng(1752)
    n = TOTAL_SAMPLES
    t = np.arange(n, dtype=np.float32) / SR
    white_l = rng.standard_normal(n).astype(np.float32)
    white_r = rng.standard_normal(n).astype(np.float32)
    # Soft rain + colonial storm wind (fades gently into starry electric hum after t=20.5s)
    storm_mask = np.clip(1.0 - (t - 19.5) / 3.5, 0.22, 1.0)
    rain_l = butter_filter(white_l, "band", (900.0, 5200.0), order=2) * 0.35 * storm_mask
    rain_r = butter_filter(white_r, "band", (900.0, 5200.0), order=2) * 0.35 * storm_mask
    wind_l = butter_filter(white_l, "band", (110.0, 380.0), order=2) * (0.45 + 0.25 * np.sin(2 * math.pi * 0.28 * t)) * storm_mask
    wind_r = butter_filter(white_r, "band", (110.0, 380.0), order=2) * (0.45 + 0.25 * np.cos(2 * math.pi * 0.23 * t)) * storm_mask
    hum_mask = np.clip((t - 19.8) / 2.2, 0.0, 1.0)
    ehum = (0.16 * np.sin(2.0 * math.pi * 120.0 * t) + 0.07 * np.sin(2.0 * math.pi * 240.0 * t)) * hum_mask
    return np.stack([rain_l + wind_l + ehum, rain_r + wind_r + ehum], axis=-1).astype(np.float32)


# ============================================================================
# SPATIAL HIGH-VOLTAGE FOLEY SFX
# ============================================================================
def synth_sfx(kind: str, pan: float, event_t: float) -> np.ndarray:
    rng = np.random.default_rng(int(round(event_t * 1000)) + abs(hash(kind)) % 10000)

    if kind == "storm_wind_swell":
        n = int(1.6 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        w = butter_filter(rng.standard_normal(n).astype(np.float32), "band", (180.0, 950.0), order=2)
        env = np.sin(math.pi * t / 1.6) ** 1.4
        return pan_sweep_stereo(w * env * 0.34, pan - 0.35, pan + 0.35)

    if kind == "distant_thunder_rumble":
        n = int(2.2 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        n_raw = rng.standard_normal(n).astype(np.float32)
        rumble = butter_filter(n_raw, "band", (38.0, 190.0), order=3)
        mod = 0.65 + 0.35 * np.sin(2.0 * math.pi * 3.8 * t) * np.exp(-t * 0.8)
        env = np.minimum(1.0, t / 0.14) * np.exp(-t * 1.15)
        return pan_stereo(rumble * mod * env * 0.52, pan)

    if kind in ("lightning_kite_strike", "rod_lightning_intercept"):
        n = int(1.65 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        n_raw = rng.standard_normal(n).astype(np.float32)
        # Razor-sharp electric whip crack + high-voltage plasma sizzle + sub-bass thunderclap!
        crack = butter_filter(n_raw, "band", (1600.0, 8800.0), order=2) * np.exp(-t * 28.0) * 1.15
        zaps = np.sign(np.sin(2.0 * math.pi * (420.0 + 1800.0 * np.exp(-t * 14.0)) * t)) * np.exp(-t * 16.0) * 0.28
        boom = butter_filter(n_raw, "band", (42.0, 210.0), order=3) * np.minimum(1.0, t / 0.015) * np.exp(-t * 1.65) * 0.92
        sub = np.sin(2.0 * math.pi * (68.0 * np.exp(-t * 2.2) + 38.0) * t) * np.exp(-t * 2.4) * 0.45
        mono = (crack + zaps + boom + sub) * (0.95 if kind == "rod_lightning_intercept" else 0.86)
        return pan_stereo(np.tanh(mono).astype(np.float32) * 0.72, pan)

    if kind == "brass_key_ting":
        n = int(0.95 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        ting = (
            0.55 * np.sin(2.0 * math.pi * 2480.0 * t) * np.exp(-t * 4.8)
            + 0.32 * np.sin(2.0 * math.pi * 4120.0 * t) * np.exp(-t * 7.2)
            + 0.20 * np.sin(2.0 * math.pi * 6380.0 * t) * np.exp(-t * 11.0)
        ) * np.minimum(1.0, t / 0.002)
        return pan_stereo(ting.astype(np.float32) * 0.44, pan)

    if kind == "knuckle_spark_snap":
        n = int(0.45 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        n_raw = rng.standard_normal(n).astype(np.float32)
        snap = butter_filter(n_raw, "band", (2200.0, 11000.0), order=2) * np.exp(-t * 42.0) * 1.3
        arc = np.sin(2.0 * math.pi * (1450.0 * np.exp(-t * 12.0) + 320.0) * t) * np.exp(-t * 24.0) * 0.45
        return pan_stereo(np.tanh((snap + arc) * 1.2).astype(np.float32) * 0.62, pan)

    if kind == "leyden_jar_charge":
        n = int(1.85 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        f = 180.0 + 520.0 * ((t / 1.85) ** 1.4)
        ph = 2.0 * math.pi * np.cumsum(f) / SR
        glass_ring = (0.45 * np.sin(ph) + 0.25 * np.sin(2.0 * ph) + 0.14 * np.sin(3.0 * ph))
        env = np.minimum(1.0, t / 0.18) * np.minimum(1.0, (1.85 - t) / 0.25)
        return pan_stereo((glass_ring * env * 0.34).astype(np.float32), pan)

    if kind == "electric_arc_crackle":
        n = int(0.55 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        n_raw = rng.standard_normal(n).astype(np.float32)
        pulses = (rng.random(n) > 0.996).astype(np.float32) * rng.uniform(-1.0, 1.0, n).astype(np.float32)
        crackle = butter_filter(n_raw * 0.25 + pulses * 3.5, "band", (1800.0, 9500.0), order=2)
        buzz = np.sin(2.0 * math.pi * 120.0 * t) * 0.18
        env = np.minimum(1.0, t / 0.015) * np.exp(-t * 4.5)
        return pan_stereo((np.tanh((crackle + buzz) * 1.4) * env * 0.44).astype(np.float32), pan)

    if kind == "grounding_drain_hiss":
        n = int(1.10 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        f = 780.0 * np.exp(-t * 2.4) + 95.0
        drain = np.sin(2.0 * math.pi * np.cumsum(f) / SR) * 0.38
        hiss = butter_filter(rng.standard_normal(n).astype(np.float32), "band", (1100.0, 6200.0), order=2) * 0.26
        env = np.minimum(1.0, t / 0.03) * np.exp(-t * 2.4)
        return pan_stereo(((drain + hiss) * env * 0.48).astype(np.float32), pan)

    if kind == "power_grid_ignition":
        n = int(1.50 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        f1 = 110.0 + 330.0 * (1.0 - np.exp(-t * 2.2))
        ph = 2.0 * math.pi * np.cumsum(f1) / SR
        hum = (0.48 * np.sin(ph) + 0.28 * np.sin(2.0 * ph) + 0.16 * np.sin(3.0 * ph))
        env = np.minimum(1.0, t / 0.15) * np.exp(-t * 1.35)
        return pan_sweep_stereo((hum * env * 0.42).astype(np.float32), -0.3, 0.3)

    if kind == "formula_shimmer":
        n = int(0.85 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        chime = (
            0.45 * np.sin(2.0 * math.pi * 1046.5 * t)
            + 0.35 * np.sin(2.0 * math.pi * 1567.98 * t)
            + 0.22 * np.sin(2.0 * math.pi * 2093.0 * t)
        ) * np.minimum(1.0, t / 0.015) * np.exp(-t * 4.2)
        return pan_stereo((chime * 0.30).astype(np.float32), pan)

    if kind == "whoosh_transition":
        n = int(0.45 * SR)
        t = np.arange(n, dtype=np.float32) / SR
        w = butter_filter(rng.standard_normal(n).astype(np.float32), "band", (260.0, 2400.0), order=2)
        env = np.sin(math.pi * t / 0.45) ** 1.6
        return pan_sweep_stereo((w * env * 0.32).astype(np.float32), pan - 0.5, pan + 0.5)

    if kind == "finale_triumph_chime":
        n = int(1.90 * SR)
        st = np.zeros((n, CHANNELS), dtype=np.float32)
        for k, (m, p) in enumerate([(72, -0.38), (79, -0.16), (84, 0.0), (88, 0.18), (91, 0.40)]):
            idx0 = int(k * 0.050 * SR)
            rem = n - idx0
            tt = np.arange(rem, dtype=np.float32) / SR
            f = midi_to_hz(m)
            bell = (
                0.58 * np.sin(2.0 * math.pi * f * tt)
                + 0.24 * np.sin(4.0 * math.pi * f * tt) * np.exp(-tt * 3.8)
            ) * np.minimum(1.0, tt / 0.010) * np.exp(-tt * 2.1)
            st[idx0:] += pan_stereo(bell.astype(np.float32) * 0.28, p)
        return (st * 0.85).astype(np.float32)

    raise ValueError(f"Unhandled SFX type: {kind}")


# ============================================================================
# BROADCAST MASTERING (-14.0 LUFS, TRUE PEAK <= -1.5 dBFS) + SUBTITLES
# ============================================================================
def measure_lufs_48k(stereo: np.ndarray) -> float:
    b1 = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285], dtype=np.float64)
    a1 = np.array([1.0, -1.69065929318241, 0.73248077421585], dtype=np.float64)
    b2 = np.array([1.0, -2.0, 1.0], dtype=np.float64)
    a2 = np.array([1.0, -1.99004745483398, 0.99007225036621], dtype=np.float64)
    y = signal.lfilter(b2, a2, signal.lfilter(b1, a1, stereo.astype(np.float64), axis=0), axis=0)
    block_len, hop_len = int(0.400 * SR), int(0.100 * SR)
    powers = [
        float(np.mean(y[s : s + block_len, 0] ** 2) + np.mean(y[s : s + block_len, 1] ** 2))
        for s in range(0, len(y) - block_len + 1, hop_len)
    ]
    p_arr = np.array(powers, dtype=np.float64)
    l_blocks = -0.691 + 10.0 * np.log10(np.maximum(p_arr, 1e-12))
    abs_mask = l_blocks > -70.0
    if not np.any(abs_mask):
        return -70.0
    rel_thresh = -0.691 + 10.0 * math.log10(max(float(np.mean(p_arr[abs_mask])), 1e-12)) - 10.0
    rel_mask = abs_mask & (l_blocks > rel_thresh)
    return -0.691 + 10.0 * math.log10(max(float(np.mean(p_arr[rel_mask])), 1e-12))


def brickwall_true_peak_limiter(stereo: np.ndarray, ceiling: float = TRUE_PEAK_CEILING_LIN) -> np.ndarray:
    out = stereo.copy().astype(np.float32)
    for _ in range(3):
        up = signal.resample_poly(out.astype(np.float64), 4, 1, axis=0)
        peak_up = np.max(np.abs(up), axis=1)
        peak_blk = peak_up.reshape(-1, 4).max(axis=1)[: len(out)].astype(np.float32)
        env = smooth_envelope(peak_blk, attack_ms=0.8, release_ms=45.0)
        env = np.maximum(env, peak_blk)
        gain = np.where(env > ceiling, ceiling / np.maximum(env, 1e-6), 1.0).astype(np.float32)
        out *= gain[:, None]
    up = signal.resample_poly(out.astype(np.float64), 4, 1, axis=0)
    tp = float(np.max(np.abs(up)))
    if tp > ceiling:
        out *= float(ceiling / tp)
    return out.astype(np.float32)


HANGING_WORDS = {
    "a", "an", "the", "of", "on", "in", "to", "with", "and", "or", "as", "so",
    "its", "his", "my", "our", "your", "into", "under", "for", "by", "at", "one",
}


def join_tokens(tokens: list[dict[str, Any]]) -> str:
    parts = []
    for i, tok in enumerate(tokens):
        w = tok["word"]
        if i == 0:
            parts.append(w)
        else:
            sep = "" if (tokens[i - 1]["word"].endswith("—") or w.startswith("—")) else " "
            parts.append(sep + w)
    return "".join(parts)


def split_clause_balanced(clause: list[dict[str, Any]], max_words: int = 7, max_chars: int = 44) -> list[list[dict[str, Any]]]:
    if len(clause) <= max_words and len(join_tokens(clause)) <= max_chars:
        return [clause]
    best_k, best_score = None, 1e9
    n = len(clause)
    for k in range(2, n - 1):
        left, right = clause[:k], clause[k:]
        lt, rt = join_tokens(left), join_tokens(right)
        score = abs(len(lt) - len(rt))
        if len(left) > max_words:
            score += (len(left) - max_words) * 40.0
        if len(lt) > max_chars:
            score += (len(lt) - max_chars) * 6.0
        if left[-1]["word"].lower().strip(".,!?—':;\"") in HANGING_WORDS:
            score += 35.0
        if left[-1]["word"].endswith((",", "—", ";", ":")):
            score -= 18.0
        if score < best_score:
            best_score, best_k = score, k
    if best_k is None:
        best_k = max(2, min(n - 2, max_words))
    return split_clause_balanced(clause[:best_k], max_words, max_chars) + split_clause_balanced(clause[best_k:], max_words, max_chars)


def chunk_words(words: list[dict[str, Any]], max_words: int = 7, max_chars: int = 44) -> list[list[dict[str, Any]]]:
    clauses: list[list[dict[str, Any]]] = []
    cur: list[dict[str, Any]] = []
    for idx, w in enumerate(words):
        cur.append(w)
        rem = len(words) - 1 - idx
        wt = w["word"]
        if ((wt.endswith(("—", ".", "!", "?", ";"))) or (wt.endswith(",") and len(cur) >= 3 and len(join_tokens(cur)) >= 20)) and len(cur) >= 2 and rem != 1:
            clauses.append(cur)
            cur = []
    if cur:
        if len(cur) == 1 and clauses:
            clauses[-1].extend(cur)
        else:
            clauses.append(cur)
    cards = [c for cl in clauses for c in split_clause_balanced(cl, max_words, max_chars)]
    merged: list[list[dict[str, Any]]] = []
    for card in cards:
        if len(card) == 1 and merged and len(merged[-1]) < max_words:
            merged[-1].extend(card)
        else:
            merged.append(card)
    return merged


def choose_line_break(ch: list[dict[str, Any]], max_single_line_chars: int = 23) -> int:
    full, n = join_tokens(ch), len(ch)
    if n <= 2 or (len(full) <= max_single_line_chars and n <= 4):
        return n
    best_k, best_score = n, 1e9
    for k in range(1, n):
        l1, l2 = join_tokens(ch[:k]), join_tokens(ch[k:])
        score = abs(len(l1) - len(l2)) * 1.2 + max(0, len(l1) - 23) * 15.0 + max(0, len(l2) - 23) * 15.0
        if n - k == 1 and n >= 4:
            score += 24.0
        if k == 1 and n >= 4:
            score += 18.0
        if ch[k - 1]["word"].lower().strip(".,!?—':;\"") in HANGING_WORDS:
            score += 30.0
        if ch[k - 1]["word"].endswith((",", "—", "!", "?")):
            score -= 12.0
        if score < best_score:
            best_score, best_k = score, k
    return best_k


def fmt_ass_time(sec: float) -> str:
    cs = int(round(max(0.0, sec) * 100))
    return f"{cs // 360000}:{(cs % 360000) // 6000:02d}:{(cs % 6000) // 100:02d}.{cs % 100:02d}"


def write_srt(manifest_lines: list[dict[str, Any]], srt_path: Path) -> None:
    def fmt_ts(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000))
        return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"

    blocks, idx, prev_end = [], 1, 0
    for line in manifest_lines:
        for ch in chunk_words(line["words"]):
            t0 = max(prev_end, int(round(max(0.0, ch[0]["start"]) * 1000)))
            t1 = max(t0 + 50, int(round(max(0.0, ch[-1]["end"]) * 1000)))
            prev_end = t1
            sp = choose_line_break(ch)
            txt = (join_tokens(ch[:sp]) + "\n" + join_tokens(ch[sp:])) if sp < len(ch) else join_tokens(ch)
            blocks.append(f"{idx}\n{fmt_ts(t0 / 1000.0)} --> {fmt_ts(t1 / 1000.0)}\n{txt}\n")
            idx += 1
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.write_text("\n".join(blocks), encoding="utf-8")


def write_word_karaoke_ass(manifest_lines: list[dict[str, Any]], ass_path: Path) -> None:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,66,&H00FFFFFF,&H00FFE040,&H00120803,&H96000000,-1,0,0,0,100,100,0,0,1,8,3.0,2,80,80,275,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    raw_events, prev_end_cs = [], 0
    for line in manifest_lines:
        for ch in chunk_words(line["words"]):
            sp = choose_line_break(ch)
            for idx, w in enumerate(ch):
                t0 = max(prev_end_cs, int(round(max(0.0, w["start"] if idx > 0 else ch[0]["start"]) * 100)))
                t1 = int(round(max(0.0, ch[idx + 1]["start"] if idx + 1 < len(ch) else w["end"]) * 100))
                if t1 <= t0:
                    t1 = t0 + 3
                prev_end_cs = t1
                parts = []
                for j, cw in enumerate(ch):
                    tok = cw["word"]
                    styled = f"{{\\c&H00FFE040&}}{tok}{{\\c&H00FFFFFF&}}" if j == idx else tok
                    if j == sp:
                        parts.append("\\N" + styled)
                    elif j == 0:
                        parts.append(styled)
                    else:
                        sep = "" if (ch[j - 1]["word"].endswith("—") or tok.startswith("—")) else " "
                        parts.append(sep + styled)
                raw_events.append((t0, t1, "".join(parts)))
    events = [f"Dialogue: 0,{fmt_ass_time(t0/100.0)},{fmt_ass_time(t1/100.0)},Default,,0,0,0,,{txt}" for t0, t1, txt in raw_events]
    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(f"[Subtitles] Exported boxless karaoke ASS: {ass_path} ({len(events)} events, 0 overlaps)")


def main() -> None:
    tl = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    tl["sfxEvents"] = [{**ev, "time": float(ev["t"])} for ev in tl.get("sfx", [])]

    print("[1/5] Synthesizing Edge-TTS American Neural Multi-Voice Dialogue (Narrator + Benjamin + William)...")
    dialogue_bus, speaker_mono_buses, manifest_lines = synthesize_dialogue(tl)

    print("[2/5] Composing 120 BPM Storm-Tension Baroque & Electric Cinema Score...")
    bgm_bus = compose_franklin_score()

    print("[3/5] Synthesizing Living Stormy Meadow -> Starry Electric-Night Ambience Bed...")
    ambience_bus = compose_storm_ambience_bed()

    print(f"[4/5] Synthesizing {len(tl['sfxEvents'])} High-Voltage Spatial Foley SFX...")
    sfx_bus = np.zeros((TOTAL_SAMPLES, CHANNELS), dtype=np.float32)
    for ev in tl["sfxEvents"]:
        add_stereo_event(sfx_bus, synth_sfx(ev["type"], float(ev.get("pan", 0.0)), float(ev["time"])), float(ev["time"]))
    sfx_bus = add_outdoor_reverb(sfx_bus, mix=0.07)

    print("[5/5] Mastering 30.000s 48kHz Stereo WAV (-14.0 LUFS, -9.5 dB Sidechain Ducking, TP <= -1.5 dBFS)...")
    # Sidechain BGM ducking (-9.5 dB under dialogue per AGENTS.md)
    dlg_env = smooth_envelope(dialogue_bus, attack_ms=15.0, release_ms=260.0)
    duck = np.clip(1.0 - np.clip(dlg_env / 0.06, 0.0, 1.0) * (1.0 - 10.0 ** (-9.5 / 20.0)), 0.30, 1.0)
    bgm_ducked = bgm_bus * duck[:, None]
    amb_ducked = ambience_bus * (0.65 + 0.35 * duck[:, None])

    core_mix = dialogue_bus * 1.15 + bgm_ducked * 0.62 + sfx_bus * 0.72
    est_gain = 10.0 ** ((TARGET_LUFS - measure_lufs_48k(core_mix)) / 20.0)
    amb_rms = float(np.sqrt(np.mean(amb_ducked[: int(29.0 * SR)] ** 2) + 1e-12))
    amb_scale = (10.0 ** (AMBIENCE_TARGET_DBFS / 20.0) / max(1e-6, amb_rms)) / max(1e-4, est_gain)
    mix = butter_filter(core_mix + amb_ducked * float(amb_scale), "high", 28.0, order=2)

    for _ in range(2):
        g = 10.0 ** ((TARGET_LUFS - measure_lufs_48k(mix)) / 20.0)
        mix = brickwall_true_peak_limiter((mix * g).astype(np.float32), ceiling=TRUE_PEAK_CEILING_LIN)

    micro = int(round(0.004 * SR))
    mix[:micro] *= np.linspace(0.0, 1.0, micro, dtype=np.float32)[:, None]
    mix[-micro:] *= np.linspace(1.0, 0.0, micro, dtype=np.float32)[:, None]

    final_lufs = measure_lufs_48k(mix)
    up_tp = signal.resample_poly(mix.astype(np.float64), 4, 1, axis=0)
    final_tp = 20.0 * math.log10(max(1e-9, float(np.max(np.abs(up_tp)))))

    master_path = PROJECT_ROOT / tl["audio"]["masterPath"]
    manifest_path = PROJECT_ROOT / tl["audio"]["manifestPath"]
    srt_path = PROJECT_ROOT / tl["audio"]["srtPath"]
    ass_path = PROJECT_ROOT / tl["audio"]["assPath"]
    master_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(master_path), mix, SR, subtype="PCM_16")

    lip_map, narrow_map = compute_lip_sync(speaker_mono_buses, LIP_FPS, LIP_TOTAL_FRAMES)
    manifest = {
        "title": tl["title"],
        "duration": DURATION,
        "fps": LIP_FPS,
        "totalFrames": LIP_TOTAL_FRAMES,
        "sampleRate": SR,
        "totalSamples": TOTAL_SAMPLES,
        "integratedLufs": round(final_lufs, 3),
        "truePeakDbfs": round(final_tp, 3),
        "lines": manifest_lines,
        "lipSync": lip_map,
        "lipNarrow": narrow_map,
        "sfxEvents": tl["sfxEvents"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_srt(manifest_lines, srt_path)
    write_word_karaoke_ass(manifest_lines, ass_path)
    print(f"[Master] {master_path.name}: LUFS={final_lufs:.2f} | TruePeak={final_tp:.2f} dBFS | 30.000s READY!")


if __name__ == "__main__":
    main()
