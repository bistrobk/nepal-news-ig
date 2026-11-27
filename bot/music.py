"""Short background tracks made from scratch (no copyright, so Instagram never mutes them).

make(path, seconds, mood, hits)  writes a mono 16-bit WAV.
mood: urgent | serious | upbeat | calm | somber
hits: times in seconds for scene changes; each gets a whoosh, the first one an impact.

Standard library only. ffmpeg resamples it when the video is muxed.
"""
import array
import math
import random
import wave

SR = 22050
TAU = 2 * math.pi
N = 2048

# (bpm, chords as semitones from A2=110 Hz, drums, arp)
MOODS = {
    "urgent": (124, [[5, 8, 12], [1, 5, 8], [-2, 1, 5], [0, 4, 7]], "drive", False),   # Dm Bb Gm A
    "serious": (90, [[0, 3, 7], [-4, 0, 3], [3, 7, 10], [-2, 2, 5]], "lofi", False),  # Am F C G
    "upbeat": (116, [[-2, 2, 5], [5, 9, 12], [7, 10, 14], [3, 7, 10]], "four", True),  # G D Em C
    "calm": (80, [[6, 10, 13, 17], [3, 6, 10, 13], [-1, 3, 6, 10], [1, 5, 8, 12]], "soft", True),
    "somber": (66, [[3, 6, 10], [-1, 3, 6], [6, 10, 13], [1, 5, 8]], None, False),   # Cm Ab Eb Bb
}


def _table(harmonics):
    t = [sum(a * math.sin(TAU * k * i / N) for k, a in harmonics) for i in range(N)]
    peak = max(abs(v) for v in t)
    return [v / peak for v in t]


SAW = _table([(k, 1 / k) for k in range(1, 9)])
SOFT = _table([(1, 1), (2, .35), (3, .15), (4, .06)])
SINE = _table([(1, 1)])


def hz(semi):
    return 110 * 2 ** (semi / 12)


def _osc(buf, start, length, f, table, amp, attack, release, decay=None):
    """Add one note to buf. decay: per-second exponential fall (plucks), else flat sustain."""
    step = f * N / SR
    ph = random.random() * N
    a_n, r_n = max(1, int(attack * SR)), max(1, int(release * SR))
    k = math.exp(-decay / SR) if decay else 1.0
    g = 1.0
    end = min(len(buf), start + length)
    for i in range(max(0, start), end):
        j = i - start
        env = min(1.0, j / a_n, (length - j) / r_n) * g
        buf[i] += table[int(ph) % N] * amp * env
        ph += step
        g *= k


def _kick(amp=1.0):
    out, ph = [], 0.0
    for i in range(int(.28 * SR)):
        t = i / SR
        f = 45 + 95 * math.exp(-t * 28)
        ph += TAU * f / SR
        out.append(math.sin(ph) * math.exp(-t * 11) * amp)
    return out


def _noise(seconds, decay, hp=True, amp=1.0, lp=0.0):
    out, prev, low = [], 0.0, 0.0
    for i in range(int(seconds * SR)):
        x = random.uniform(-1, 1)
        y = x - prev if hp else x
        prev = x
        if lp:
            low += lp * (y - low)
            y = low
        out.append(y * math.exp(-i / SR * decay) * amp)
    return out


def _add(buf, start, sample):
    for j, v in enumerate(sample):
        i = start + j
        if 0 <= i < len(buf):
            buf[i] += v


def _whoosh(seconds=.7):
    """Filtered noise that rises and stops at the cut (reversed swell)."""
    n = int(seconds * SR)
    out, low = [], 0.0
    for i in range(n):
        p = i / n
        low += (0.02 + 0.25 * p) * (random.uniform(-1, 1) - low)
        out.append(low * p ** 2 * 1.6)
    return out


def _lowpass(buf, alpha):
    y = 0.0
    for i, v in enumerate(buf):
        y += alpha * (v - y)
        buf[i] = y


def make(path, seconds, mood="serious", hits=()):
    random.seed(7)
    bpm, chords, drums, arp = MOODS.get(mood, MOODS["serious"])
    total = int(seconds * SR)
    beat = 60 / bpm
    bar = int(4 * beat * SR)
    pad = [0.0] * total
    music = [0.0] * total
    duck = [1.0] * total

    # pad: two detuned saws per note, one chord per bar, low-passed later
    for b, start in enumerate(range(0, total, bar)):
        for s in chords[b % len(chords)]:
            for det in (-0.08, 0.08):
                _osc(pad, start, bar + int(.15 * SR), hz(s + 12 + det), SAW, .07, .35, .5)
        root = chords[b % len(chords)][0]
        if drums == "drive":  # pulsing 8th-note bass
            for k in range(8):
                _osc(music, start + int(k * beat / 2 * SR), int(beat / 2 * SR * .9), hz(root - 12),
                     SOFT, .30, .005, .05)
        else:
            _osc(music, start, bar, hz(root - 12), SOFT, .26 if drums else .18, .05, .4)
        if arp:  # 8th-note arpeggio pluck, up an octave
            notes = chords[b % len(chords)]
            for k in range(8):
                n = notes[k % len(notes)] + 24 + (12 if k in (3, 7) else 0)
                _osc(music, start + int(k * beat / 2 * SR), int(beat * SR), hz(n), SOFT,
                     .09, .003, .1, decay=9)
        if not drums:  # somber: slow piano-like notes instead of drums
            for k, n in enumerate(chords[b % len(chords)]):
                _osc(music, start + int(k * beat * SR), int(beat * 2 * SR), hz(n + 24), SOFT,
                     .11, .004, .2, decay=3)
    _lowpass(pad, 0.10 if mood in ("calm", "somber") else 0.16)

    # drums
    kick, hat = _kick(.9), _noise(.04, 90, amp=.25)
    snare = _noise(.18, 22, hp=False, amp=.32, lp=.5)
    nbeats = int(seconds / beat) + 1
    for k in range(nbeats):
        t0 = int(k * beat * SR)
        if drums is None:
            continue
        on_kick = {"drive": True, "four": True, "lofi": k % 4 in (0, 2) or k % 8 == 7,
                   "soft": k % 4 == 0}[drums]
        if on_kick:
            _add(music, t0, kick)
            for j in range(int(.22 * SR)):  # sidechain the pad under each kick
                if t0 + j < total:
                    duck[t0 + j] = min(duck[t0 + j], .35 + .65 * j / (.22 * SR))
        if drums in ("lofi", "four", "drive") and k % 2 == 1:
            _add(music, t0, snare)
        if drums != "soft":
            for h in (0, .5):
                _add(music, t0 + int(h * beat * SR), hat if h else [v * .5 for v in hat])

    # sound design synced to the cuts
    sfx = [0.0] * total
    for n, t in enumerate(hits):
        w = _whoosh()
        _add(sfx, int(t * SR) - len(w), [v * .45 for v in w])
        if n == 0:
            _add(sfx, int(t * SR), [v * 1.1 for v in _kick()])
            _add(sfx, int(t * SR), _noise(.5, 6, hp=False, amp=.18, lp=.08))

    fade_in, fade_out = int(.25 * SR), int(1.2 * SR)
    mix = []
    for i in range(total):
        v = pad[i] * duck[i] + music[i] + sfx[i]
        v *= min(1.0, i / fade_in, (total - i) / fade_out)
        mix.append(v)
    peak = max(1e-9, max(abs(v) for v in mix))
    gain = 0.89 / peak
    data = array.array("h", (int(math.tanh(v * gain * 1.2) / math.tanh(1.2) * 32000) for v in mix))
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.tobytes())
    return path
