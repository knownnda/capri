/* Capri's "beep voice": a little synth blip for every letter as her words type out (classic RPG dialogue style),
   tuned to her: a bright, punchy, slightly digital square-wave voice that jumps around a pentatonic scale
   (so sentences sound like speech, not a single tone), rises at the end of questions and shifts with her mood.
   100% generated in the browser with WebAudio: no audio files, works offline, costs nothing.

   Settings it reads (right-click > VOICE):
     voice_engine: "beeps" (default) | "piper" | "voicebox" | "api" | "off"
     voice_pitch:  "low" | "normal" (default) | "high"
     voice_volume: 0..1 (default 0.6)                                                        */
(function(){
  const BASE = {low: 330, normal: 440, high: 587};          // her pitch centre (Hz). Toriel-style beeps sit ~300 Hz; Capri is brighter
  const SCALE = [0, 2, 4, 7, 9, 12];                         // major pentatonic steps: always sounds "melodic"
  const MOOD = {hyped: 3, greet: 2, idle: 0, talking: 0, working: -1, alert: -3};
  let ac = null, sq = null, sw = null, amp = null, last = 0, idleT = null;

  /* ONE small audio graph, built once and reused for every blip (square + octave saw -> envelope -> low-pass -> compressor).
     Creating new oscillators for every letter (hundreds per reply) can crash the embedded browser's audio thread on some PCs,
     so blips only move the pitch and the volume envelope of these same nodes. When she's quiet the audio context is suspended. */
  function audio(){
    if (!ac){
      ac = new (window.AudioContext || window.webkitAudioContext)({latencyHint: "interactive"});
      const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 3600; lp.Q.value = 0.9;
      const comp = ac.createDynamicsCompressor(); comp.threshold.value = -18; comp.ratio.value = 4;
      amp = ac.createGain(); amp.gain.value = 0;
      sq = ac.createOscillator(); sq.type = "square"; sq.frequency.value = 440;
      sw = ac.createOscillator(); sw.type = "sawtooth"; sw.frequency.value = 880;
      const swg = ac.createGain(); swg.gain.value = 0.22;
      sq.connect(amp); sw.connect(swg); swg.connect(amp); amp.connect(lp); lp.connect(comp); comp.connect(ac.destination);
      sq.start(); sw.start();
    }
    if (ac.state !== "running") ac.resume().catch(() => {});
    clearTimeout(idleT); idleT = setTimeout(() => { try{ if (ac && ac.state === "running") ac.suspend(); }catch(e){} }, 4000);
    return ac;
  }

  function hash(ch){ const c = ch.toLowerCase().codePointAt(0) || 0; return (c * 7 + (c >> 3)) % SCALE.length; }

  /* one blip. ch = the letter being typed, o = {pitch, volume, mood, question, emphasis} */
  function blip(ch, o){
    o = o || {};
    let a; try{ a = audio(); }catch(e){ return; }
    const t = a.currentTime + 0.005;
    if (t - last < 0.03) return;                             // never machine-gun, and never overlap two envelopes
    last = t;
    const vowel = /[aeiouyáéíóúàèìòùäëïöüâêîôû]/i.test(ch);
    let semis = SCALE[hash(ch)] + (vowel ? 2 : 0) + (MOOD[o.mood] || 0) + (o.question ? 3 : 0) + (o.emphasis ? 2 : 0);
    semis += (Math.random() - 0.5) * 0.6;                    // a hair of human wobble
    const f = (BASE[o.pitch] || BASE.normal) * Math.pow(2, semis / 12);
    const vol = 0.11 * (o.volume == null ? 0.6 : +o.volume);
    const dur = vowel ? 0.062 : 0.046;
    try{
      sq.frequency.cancelScheduledValues(t); sw.frequency.cancelScheduledValues(t); amp.gain.cancelScheduledValues(t);
      sq.frequency.setValueAtTime(f, t); sq.frequency.linearRampToValueAtTime(f * (o.question ? 1.06 : 0.985), t + dur);   // tiny glide = voice-like
      sw.frequency.setValueAtTime(f * 2.004, t);
      amp.gain.setValueAtTime(0, t);
      amp.gain.linearRampToValueAtTime(vol, t + 0.004);       // instant attack (the "click" of a beep)
      amp.gain.setValueAtTime(vol, t + dur * 0.55);
      amp.gain.linearRampToValueAtTime(0, t + dur);
    }catch(e){}
  }

  /* how long to wait after typing `ch` (ms). Long replies type faster so she never drags. */
  function delay(ch, length){
    const base = length > 260 ? 16 : length > 140 ? 22 : 30;
    if (/[.!?…]/.test(ch)) return base * 5;
    if (/[,;:]/.test(ch)) return base * 3;
    if (ch === "\n") return base * 4;
    if (ch === " ") return base * 0.7;
    return base;
  }
  /* does this character get a blip? letters/numbers only, and every 2nd one on very long replies */
  function sounds(ch, index, length){
    if (!/[\p{L}\p{N}]/u.test(ch)) return false;
    return length > 260 ? index % 2 === 0 : true;
  }

  /* ---- a typewriter that follows text as it streams in, blipping as it goes ---- */
  function Typer(render){
    this.render = render; this.target = ""; this.i = 0; this.t = null; this.end = null; this.opts = {};
  }
  Typer.prototype.start = function(text, opts, end){ this.stop(); this.target = text || ""; this.i = 0; this.opts = opts || {}; this.end = end || null; this.render(""); this._step(); };
  Typer.prototype.follow = function(text, opts){            // streaming: keep typing towards the newest text
    if (opts) this.opts = opts;
    if (!text.startsWith(this.target.slice(0, this.i))) return this.start(text, this.opts, this.end);
    this.target = text; if (!this.t) this._step();
  };
  Typer.prototype.finish = function(text, end){              // final text is known: call end() once it's all typed
    this.end = end || null; this.follow(text);
    if (!this.t && this.i >= this.target.length && this.end){ const e = this.end; this.end = null; e(); }
  };
  Typer.prototype.stop = function(){ clearTimeout(this.t); this.t = null; this.end = null; };
  Typer.prototype.busy = function(){ return !!this.t; };
  Typer.prototype._step = function(){
    const T = this;
    if (T.i >= T.target.length){ T.t = null; if (T.end){ const e = T.end; T.end = null; e(); } return; }
    const ch = T.target[T.i], n = T.target.length, idx = T.i++;
    T.render(T.target.slice(0, T.i));
    if (T.opts.sound !== false && sounds(ch, idx, n)){
      const tail = T.target.slice(idx, idx + 14);
      blip(ch, Object.assign({}, T.opts, {question: /^[^.!?]*\?/.test(tail) && tail.indexOf("?") < 6, emphasis: /^[^.!?]*!/.test(tail) && tail.indexOf("!") < 4}));
    }
    T.t = setTimeout(() => T._step(), T.opts.sound === false ? 7 : delay(ch, n));
  };

  window.CapriVoice = {blip, Typer, unlock: audio,
    engine: s => (s && s.voice_engine) || "beeps",
    test(opts){ const t = new Typer(() => {}); t.start("Hey choom, this is my voice. Like it?", Object.assign({}, opts)); }};
})();
