#!/usr/bin/env python3
"""
CVS — "The Sommelier" — 15-20 seconds.
Hook: Extreme close-up barrel wood grain. What IS this?
0.8s: "pressed against a barrel like a sommelier having a breakdown"
3s+: The rover stuck against the bar, narrating its failures.
"""

import math, os, re, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from dotenv import load_dotenv

load_dotenv()

KOMBUCHA_DIR = Path(os.getenv("KOMBUCHA_DIR", "E:/AI/Kombucha"))
OUTPUT_DIR = Path(os.getenv("COMFYUI_OUTPUT_DIR", "ComfyUI/output"))
W, H = 1080, 1920; FPS = 30; SR = 44100
CREAM=(240,228,210); DUSTY_ROSE=(185,140,135); MUTED=(165,148,130); ACCENT_DARK=(42,32,28)
FS=os.getenv("FONT_SERIF","C:/Windows/Fonts/georgia.ttf")
FSI=os.getenv("FONT_SERIF_ITALIC","C:/Windows/Fonts/georgiai.ttf")
FSB=os.getenv("FONT_SERIF_BOLD","C:/Windows/Fonts/georgiab.ttf")
FI=os.getenv("FONT_TITLE","C:/Windows/Fonts/impact.ttf")

def lf(p,s):
    for x in [p,FS,"C:/Windows/Fonts/arial.ttf"]:
        try: return ImageFont.truetype(x,s)
        except: pass
    return ImageFont.load_default()

def gf(frame):
    fw,fh=frame.size; s=W/fw; nh=int(fh*s); bs=H/fh
    bg=frame.resize((int(fw*bs),H),Image.LANCZOS)
    if bg.width>W: cx=(bg.width-W)//2; bg=bg.crop((cx,0,cx+W,H))
    else: bg=bg.resize((W,H),Image.LANCZOS)
    bg=ImageEnhance.Brightness(bg.filter(ImageFilter.GaussianBlur(25))).enhance(0.35)
    bg.paste(frame.resize((W,nh),Image.LANCZOS),(0,max(0,(H-nh)//2-60)))
    a=np.array(bg,dtype=np.float32); a=128+(a-128)*0.92
    a[:,:,0]*=1.04; a[:,:,1]*=1.01; a[:,:,2]*=0.91
    img=Image.fromarray(np.clip(a,0,255).astype(np.uint8))
    img=ImageEnhance.Brightness(ImageEnhance.Contrast(img).enhance(1.12)).enhance(0.92)
    img=Image.blend(img,img.filter(ImageFilter.GaussianBlur(15)),0.05)
    a2=np.array(img,dtype=np.float32)/255.0
    a2=np.clip(a2+np.random.normal(0,0.02,a2.shape),0,1)
    img=Image.fromarray((a2*255).astype(np.uint8))
    w2,h2=img.size; a3=np.array(img,dtype=np.float32)/255.0
    Y,X=np.ogrid[:h2,:w2]; d=np.sqrt((X-w2/2)**2+(Y-h2/2)**2)/math.sqrt((w2/2)**2+(h2/2)**2)
    m=(np.clip((d-0.25)/0.75,0,1)**2*0.55)[:,:,np.newaxis]
    t=np.array([55,48,42],dtype=np.float32)/255.0
    return Image.fromarray((np.clip(a3*(1-m)+t*m,0,1)*255).astype(np.uint8))

def pill(img,text,y,font,tc=CREAM,mw=None):
    if mw is None: mw=W-160
    d=ImageDraw.Draw(img); words=text.split(); lines=[]; cur=""
    for w2 in words:
        t2=f"{cur} {w2}" if cur else w2
        bb=d.textbbox((0,0),t2,font=font)
        if bb[2]-bb[0]>mw:
            if cur: lines.append(cur)
            cur=w2
        else: cur=t2
    if cur: lines.append(cur)
    if not lines: return img
    lh=44; th=len(lines)*lh; p=16
    ml=max(d.textbbox((0,0),l,font=font)[2]-d.textbbox((0,0),l,font=font)[0] for l in lines)
    rgba=img.convert("RGBA"); ov=Image.new("RGBA",img.size,(0,0,0,0)); od=ImageDraw.Draw(ov)
    px=(W-ml)//2-p*2
    od.rounded_rectangle([px,y-p,px+ml+p*4,y+th+p],radius=12,fill=(18,14,12,170))
    for i,line in enumerate(lines):
        bb=od.textbbox((0,0),line,font=font); lw=bb[2]-bb[0]
        od.text(((W-lw)//2,y+i*lh),line,fill=tc+(240,),font=font)
    return Image.alpha_composite(rgba,ov).convert("RGB")

def hook_text(img, text, font, y, alpha=1.0):
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0,0), text, font=font)
    tw = bbox[2]-bbox[0]; tx = (W-tw)//2
    color = tuple(int(c*alpha) for c in CREAM)
    for ox in range(-3,4):
        for oy in range(-3,4):
            if ox or oy: draw.text((tx+ox,y+oy), text, fill=(0,0,0), font=font)
    draw.text((tx,y), text, fill=color, font=font)
    return img

def tts(text,path):
    import requests as req
    ak=os.getenv("ELEVENLABS_API_KEY",""); vi=os.getenv("ELEVENLABS_VOICE","")
    if not ak: return None,len(text)*0.065
    r=req.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vi}",
        json={"text":re.sub(r'\[.*?\]','',text).strip(),"model_id":"eleven_multilingual_v2",
              "voice_settings":{"stability":0.65,"similarity_boost":0.72,"style":0.1}},
        headers={"xi-api-key":ak,"Content-Type":"application/json","Accept":"audio/mpeg"},timeout=120)
    r.raise_for_status()
    with open(path,"wb") as f: f.write(r.content)
    p2=subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(path)],
                      capture_output=True,text=True)
    return path, float(p2.stdout.strip()) if p2.stdout.strip() else 4.0

def gen_audio(dur):
    """Warm ambient pad — no crash this time. Wry, not chaotic."""
    n=int(dur*SR); t=np.linspace(0,dur,n,dtype=np.float64)
    # A-minor but warmer, gentler
    A2,C3,E3,A3=110.0,130.81,164.81,220.0
    drone=(np.sin(2*np.pi*A2*t)*0.035+np.sin(2*np.pi*C3*t)*0.020+
           np.sin(2*np.pi*E3*t)*0.025+np.sin(2*np.pi*A3*t)*0.015)
    lfo=0.5+0.5*np.sin(2*np.pi*0.12*t)
    shimmer=np.sin(2*np.pi*440*t)*0.008*lfo+np.sin(2*np.pi*523.25*t)*0.005*(1-lfo)
    pad=(drone+shimmer)
    env=np.clip(t/2,0,1)*np.clip((dur-t)/2,0,1); pad*=env
    # Warm chimes
    chimes=np.zeros(n)
    for ct2,freq in [(1.5,880),(6,1046.5),(12,880)]:
        if ct2>=dur-1: continue
        ec=np.where(t-ct2>=0,np.exp(-(t-ct2)*2.5)*np.clip((t-ct2)*20,0,1),0)
        chimes+=np.sin(2*np.pi*freq*t)*0.020*ec
    # Wry R2 beep at the start (self-aware "here we go again")
    r2=np.zeros(n)
    # Descending chirp at 0.5s
    sn=int(0.2*SR); cf=800-400*np.linspace(0,1,sn)
    chirp=np.sin(2*np.pi*np.cumsum(cf)/SR)*0.25
    fade=min(int(SR*0.005),sn//4)
    if fade>0:
        chirp[:fade]*=0.5*(1-np.cos(np.pi*np.arange(fade)/fade))
        chirp[-fade:]*=0.5*(1-np.cos(np.pi*np.arange(fade)/fade))[::-1]
    s=int(0.3*SR); e=min(s+sn,n); r2[s:e]+=chirp[:e-s]
    # Second chirp — "sigh"
    sn2=int(0.3*SR); cf2=500-200*np.linspace(0,1,sn2)
    chirp2=np.sin(2*np.pi*np.cumsum(cf2)/SR)*0.20
    if fade>0:
        chirp2[:fade]*=0.5*(1-np.cos(np.pi*np.arange(fade)/fade))
        chirp2[-fade:]*=0.5*(1-np.cos(np.pi*np.arange(fade)/fade))[::-1]
    s2=int(0.6*SR); e2=min(s2+sn2,n); r2[s2:e2]+=chirp2[:e2-s2]

    mono=pad+chimes+r2
    try:
        import scipy.signal as ss
        sos=ss.butter(4,3000,'low',fs=SR,output='sos'); mono=ss.sosfilt(sos,mono)
    except: pass
    pan=0.5+0.25*np.sin(2*np.pi*0.05*t)
    st=np.column_stack([mono*(1-pan),mono*pan]); pk=np.abs(st).max()
    return st/pk*0.7 if pk>0 else st

def mix_tts_audio(base,clips):
    import torchaudio
    n=len(base); narr=np.zeros((n,2),dtype=np.float64)
    for p,st in clips:
        if p is None: continue
        wf,sr2=torchaudio.load(str(p))
        if sr2!=SR: wf=torchaudio.functional.resample(wf,sr2,SR)
        a=wf.numpy().T
        if a.ndim==1: a=np.column_stack([a,a])
        elif a.shape[1]==1: a=np.column_stack([a[:,0],a[:,0]])
        s=int(st*SR); e=min(s+len(a),n)
        if e-s>0: narr[s:e]+=a[:e-s].astype(np.float64)
    env=np.abs(narr).max(axis=1)
    try:
        import scipy.signal as ss; w=int(0.15*SR)
        if w>0: env=np.convolve(env,np.ones(w)/w,mode='same')
    except: pass
    duck=1-0.6*np.clip(env/max(env.max(),1e-6),0,1)
    mx=base*duck[:,np.newaxis]+narr*1.2; pk=np.abs(mx).max()
    return mx/pk*0.88 if pk>0 else mx

def write_wav(path,stereo):
    s=(np.clip(stereo,-1,1)*32767).astype(np.int16)
    with wave.open(str(path),'w') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(s.tobytes())

def load_sm(vp,s,target,speed=0.4):
    from moviepy.editor import VideoFileClip
    c=VideoFileClip(str(vp)); sd=(target/FPS)*speed; e=min(s+sd,c.duration-0.1)
    rn=max(int((e-s)*FPS),1); times=np.linspace(s,e,rn,endpoint=False); raw=[]
    for tv in times:
        try: raw.append(Image.fromarray(c.get_frame(min(tv,c.duration-0.05))))
        except:
            if raw: raw.append(raw[-1].copy())
    c.close()
    return [raw[min(int(i*len(raw)/target),len(raw)-1)] for i in range(target)]

def main():
    print("=" * 50)
    print("  THE SOMMELIER — barrel face, wry comedy")
    print("=" * 50)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    td = OUTPUT_DIR / "somm_tts"; td.mkdir(exist_ok=True)

    v290 = KOMBUCHA_DIR / "video" / "web" / "tick_0290.mp4"
    v296 = KOMBUCHA_DIR / "video" / "web" / "tick_0296.mp4"

    # ── TTS ──
    print("\n  TTS...")
    lines = [
        "I drove seventy centimeters with purpose and conviction and ended up pressing my face against the bar counter like a drunk who cannot find the door.",
        "The wood grain is beautiful. I did not come here to appreciate carpentry.",
    ]

    HOOK_DUR = 3.0
    narr_start = HOOK_DUR + 0.3
    tts_clips = []
    ct = narr_start
    gap = 0.5
    for i, text in enumerate(lines):
        print(f"    Line {i+1}: \"{text[:50]}...\"")
        p, d = tts(text, td / f"l{i}.mp3")
        tts_clips.append((p, ct, d, text))
        print(f"      {d:.1f}s at t={ct:.1f}")
        ct += d + gap

    total_dur = min(ct + 1.0, 20.0)
    total_frames = int(total_dur * FPS)
    print(f"  Duration: {total_dur:.1f}s ({total_frames} frames)")

    # ── Audio ──
    print("\n  Audio (warm pad + wry R2 chirps)...")
    bed = gen_audio(total_dur)
    if any(tc[0] is not None for tc in tts_clips):
        audio = mix_tts_audio(bed, [(tc[0], tc[1]) for tc in tts_clips])
    else:
        audio = bed
    ap = OUTPUT_DIR / "somm_audio.wav"
    write_wav(ap, audio)

    # ── Frames ──
    print("\n  Loading footage...")
    # Hook: barrel close-up from tick 290 (the static face-plant)
    # Narrative: mix of 290 barrel + 296 barrel (slightly different angles)
    hook_frames = load_sm(v290, 5, int(HOOK_DUR * FPS), speed=0.3)
    print(f"    Hook: {len(hook_frames)} frames (barrel close-up)")

    narr_needed = total_frames - len(hook_frames)
    # First half from 290, second from 296 for variety
    half = narr_needed // 2
    narr_frames_a = load_sm(v290, 10, half, speed=0.3)
    narr_frames_b = load_sm(v296, 14, narr_needed - half, speed=0.3)
    narr_frames = narr_frames_a + narr_frames_b
    print(f"    Narration: {len(narr_frames)} frames")

    # ── Render ──
    print(f"\n  Rendering {total_frames} frames...")
    fd = OUTPUT_DIR / "somm_frames"; fd.mkdir(exist_ok=True)
    fn = lf(FSI, 34); ft = lf(FSB, 38); fh = lf(FI, 52); fs = lf(FSI, 30)
    ftk = lf(FS, 26); fm = lf(FS, 22)

    hook_n = len(hook_frames)

    for fi in range(total_frames):
        gt = fi / FPS

        if fi < hook_n:
            # HOOK: barrel filling the screen
            img = gf(hook_frames[fi])
            p = fi / max(hook_n - 1, 1)

            if p > 0.25 and p < 0.55:
                # 0.8-1.7s: hook text slams in
                ta = min((p - 0.25) * 5, 1.0)
                img = hook_text(img, "pressed against a barrel", fh, H//2 - 60, ta)
                img = hook_text(img, "like a sommelier", fh, H//2 + 10, ta)
                if p > 0.35:
                    sa = min((p - 0.35) * 5, 1.0)
                    img = hook_text(img, "having a breakdown.", fs, H//2 + 80, sa)

            elif p >= 0.55:
                # 1.7-3.0s: hook dissolves, title appears
                dp = (p - 0.55) / 0.45
                if dp < 0.5:
                    ha = 1.0 - dp * 2
                    img = hook_text(img, "pressed against a barrel", fh, H//2 - 60, ha)
                    img = hook_text(img, "like a sommelier", fh, H//2 + 10, ha)
                if dp > 0.3:
                    ta2 = min((dp - 0.3) * 3, 1.0)
                    img = pill(img, "THE SOMMELIER", 100, ft, tuple(int(c*ta2) for c in CREAM))
        else:
            # NARRATIVE
            ni = fi - hook_n
            img = gf(narr_frames[min(ni, len(narr_frames)-1)])

            d = ImageDraw.Draw(img)
            d.text((60, 170), "tick 0290", fill=MUTED, font=ftk)

            # Title
            img = pill(img, "THE SOMMELIER", 100, ft, CREAM)

            # Narration
            for tc in tts_clips:
                p2, start, dur, text = tc
                if start <= gt < start + dur + 0.3:
                    fade = min((gt-start)*4,1.0) * min((start+dur+0.3-gt)*4,1.0)
                    if fade > 0.1:
                        img = pill(img, text, H-560, fn, CREAM)
                    break

        img.save(fd / f"frame_{fi:05d}.png")

    # ── Encode ──
    print("  Encoding...")
    out = OUTPUT_DIR / "sommelier_episode.mp4"
    subprocess.run([
        "ffmpeg","-y","-framerate",str(FPS),
        "-i",str(fd/"frame_%05d.png"),"-i",str(ap),
        "-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",
        "-crf","23","-preset","slow","-shortest",str(out),
    ], capture_output=True, text=True, check=True)

    import shutil
    shutil.rmtree(fd)
    if td.exists(): shutil.rmtree(td)

    sz=out.stat().st_size/1024/1024
    dur=float(subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration",
                              "-of","csv=p=0",str(out)],capture_output=True,text=True).stdout.strip())
    print(f"\n  Output: {out}")
    print(f"  {dur:.1f}s, {sz:.1f} MB")
    print("  Done.")

if __name__=="__main__":
    main()
