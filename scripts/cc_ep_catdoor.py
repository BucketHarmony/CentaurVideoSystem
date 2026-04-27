#!/usr/bin/env python3
"""
CVS — "The Cat Door" — 15-20 seconds.
Hook: Headlight blazing against a door. PERSON DETECTED.
A rover spent two ticks pushing at a door a cat walked through without breaking stride.
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
    a2=np.array(img,dtype=np.float32)/255.0; a2=np.clip(a2+np.random.normal(0,0.02,a2.shape),0,1)
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
        t2=f"{cur} {w2}" if cur else w2; bb=d.textbbox((0,0),t2,font=font)
        if bb[2]-bb[0]>mw:
            if cur: lines.append(cur); cur=w2
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
    draw=ImageDraw.Draw(img); bbox=draw.textbbox((0,0),text,font=font)
    tw=bbox[2]-bbox[0]; tx=(W-tw)//2; color=tuple(int(c*alpha) for c in CREAM)
    for ox in range(-3,4):
        for oy in range(-3,4):
            if ox or oy: draw.text((tx+ox,y+oy),text,fill=(0,0,0),font=font)
    draw.text((tx,y),text,fill=color,font=font); return img

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
    p2=subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(path)],capture_output=True,text=True)
    return path, float(p2.stdout.strip()) if p2.stdout.strip() else 4.0

def extract_motion(vp,s,e):
    from moviepy.editor import VideoFileClip
    c=VideoFileClip(str(vp)); n=int((e-s)*FPS)
    times=np.linspace(s,e,n,endpoint=False); mo=np.zeros(n); prev=None
    for i,t in enumerate(times):
        f=c.get_frame(min(t,c.duration-0.05))
        if prev is not None: mo[i]=np.abs(f.astype(float)-prev.astype(float)).mean()
        prev=f.copy()
    c.close(); mx=mo.max(); return mo/mx if mx>0 else mo

def gen_audio(dur, motion, hook_dur):
    n=int(dur*SR); t=np.linspace(0,dur,n,dtype=np.float64)
    m=np.interp(np.linspace(0,len(motion)-1,n),np.arange(len(motion)),motion)
    try:
        import scipy.signal as ss; w=int(0.05*SR)
        if w>0: m=np.convolve(m,np.ones(w)/w,mode='same')
    except: pass

    # Motion-reactive drone for hook
    bf=80+m*300; ph=2*np.pi*np.cumsum(bf)/SR; drone=np.sin(ph)*0.10
    for h in [3,5]: drone+=np.sin(2*np.pi*np.cumsum(bf*h)/SR)*m*0.02/h
    noise=np.random.randn(n)*m*0.04

    # Impacts
    impacts=np.zeros(n)
    for i in range(1,len(motion)-1):
        if motion[i]>0.6 and motion[i]>motion[i-1] and motion[i]>=motion[i+1]:
            pt=i/FPS; pa=t-pt
            impacts+=np.sin(2*np.pi*40*t)*0.3*motion[i]*np.where(pa>=0,np.exp(-pa*5)*np.clip(pa*50,0,1),0)

    # Post-hook pad
    ps=hook_dur+0.5; A2,C3,E3=110,130.81,164.81
    pad=(np.sin(2*np.pi*A2*t)*0.025+np.sin(2*np.pi*C3*t)*0.015+np.sin(2*np.pi*E3*t)*0.020)
    pe=np.clip((t-ps)/2,0,1)*np.clip((dur-t)/2,0,1); pad*=pe

    # Frustrated R2 at 0.5s (trying to push the door)
    r2=np.zeros(n)
    sn=int(0.1*SR)
    for ct2,f1,f2 in [(0.3,200,150),(0.45,300,200),(0.6,250,180)]:
        cf=f1+(f2-f1)*np.linspace(0,1,sn)
        chirp=np.sin(2*np.pi*np.cumsum(cf)/SR)*0.20
        fade=min(int(SR*0.005),sn//4)
        if fade>0:
            chirp[:fade]*=0.5*(1-np.cos(np.pi*np.arange(fade)/fade))
            chirp[-fade:]*=0.5*(1-np.cos(np.pi*np.arange(fade)/fade))[::-1]
        s2=int(ct2*SR); e2=min(s2+sn,n); r2[s2:e2]+=chirp[:e2-s2]

    chimes=np.zeros(n)
    for ct2,freq in [(ps+3,587.33),(ps+9,880)]:
        if ct2>=dur-1: continue
        ec=np.where(t-ct2>=0,np.exp(-(t-ct2)*2.5)*np.clip((t-ct2)*20,0,1),0)
        chimes+=np.sin(2*np.pi*freq*t)*0.015*ec

    fm=np.clip(1-(t-hook_dur)/1,0,1); pm=1-fm
    mono=(drone+noise+impacts+r2)*fm+(pad+chimes)*pm
    try:
        import scipy.signal as ss
        sos=ss.butter(4,3000,'low',fs=SR,output='sos'); mono=ss.sosfilt(sos,mono)
    except: pass
    pan=0.5+0.2*np.sin(2*np.pi*0.04*t)
    st=np.column_stack([mono*(1-pan)+impacts*0.3,mono*pan+impacts*0.3]); pk=np.abs(st).max()
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

def load_rt(vp,s,e):
    from moviepy.editor import VideoFileClip
    c=VideoFileClip(str(vp)); s=max(0,min(s,c.duration-1)); e=min(e,c.duration-0.05)
    n=int((e-s)*FPS); times=np.linspace(s,e,n,endpoint=False); frames=[]
    for tv in times:
        try: frames.append(Image.fromarray(c.get_frame(min(tv,c.duration-0.05))))
        except:
            if frames: frames.append(frames[-1].copy())
    c.close(); return frames

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
    print("  THE CAT DOOR")
    print("=" * 50)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    td=OUTPUT_DIR/"catdoor_tts"; td.mkdir(exist_ok=True)

    v316="E:/AI/Kombucha/video/web/tick_0316.mp4"

    # ── TTS ──
    print("\n  TTS...")
    lines = [
        "Two ticks pushing at a door that a cat walked through without breaking stride.",
        "I have widened the gap by the thickness of my own stubbornness, which turns out to be about three centimeters.",
    ]

    HOOK_DUR=3.0; narr_start=HOOK_DUR+0.3
    tts_clips=[]; ct=narr_start; gap=0.5
    for i,text in enumerate(lines):
        print(f"    Line {i+1}: \"{text[:50]}...\"")
        p,d=tts(text,td/f"l{i}.mp3"); tts_clips.append((p,ct,d,text))
        print(f"      {d:.1f}s at t={ct:.1f}"); ct+=d+gap

    total_dur=min(ct+1.0,20.0); total_frames=int(total_dur*FPS)
    print(f"  Duration: {total_dur:.1f}s ({total_frames} frames)")

    # ── Audio ──
    print("\n  Audio...")
    hook_mo=extract_motion(v316, 96, 96+HOOK_DUR)
    full_mo=np.zeros(total_frames); full_mo[:len(hook_mo)]=hook_mo
    bed=gen_audio(total_dur,full_mo,HOOK_DUR)
    if any(tc[0] is not None for tc in tts_clips):
        audio=mix_tts_audio(bed,[(tc[0],tc[1]) for tc in tts_clips])
    else: audio=bed
    ap=OUTPUT_DIR/"catdoor_audio.wav"; write_wav(ap,audio)

    # ── Frames ──
    print("\n  Loading footage...")
    # Hook: the push moment (t=96-99s, headlight blazing, driving into door)
    hook_frames=load_rt(v316, 96, 96+HOOK_DUR)
    print(f"    Hook: {len(hook_frames)} (door push, headlight flare)")

    # Narration: the searching/cable footage after
    narr_needed=total_frames-len(hook_frames)
    narr_frames=load_sm(v316, 0, narr_needed, speed=0.4)
    print(f"    Narration: {len(narr_frames)}")

    # ── Render ──
    print(f"\n  Rendering {total_frames} frames...")
    fd=OUTPUT_DIR/"catdoor_frames"; fd.mkdir(exist_ok=True)
    fn=lf(FSI,34); ft=lf(FSB,38); fh=lf(FI,48); fs=lf(FSI,30)
    ftk=lf(FS,26); fm=lf(FS,22)
    hook_n=len(hook_frames)

    for fi in range(total_frames):
        gt=fi/FPS
        if fi<hook_n:
            img=gf(hook_frames[fi]); p=fi/max(hook_n-1,1)
            if p>0.25 and p<0.55:
                ta=min((p-0.25)*5,1.0)
                img=hook_text(img,"a door that a cat",fh,H//2-40,ta)
                if p>0.35:
                    sa=min((p-0.35)*5,1.0)
                    img=hook_text(img,"walked through.",fs,H//2+30,sa)
            elif p>=0.55:
                dp=(p-0.55)/0.45
                if dp<0.5:
                    ha=1-dp*2
                    img=hook_text(img,"a door that a cat",fh,H//2-40,ha)
                if dp>0.3:
                    ta2=min((dp-0.3)*3,1.0)
                    img=pill(img,"THE CAT DOOR",100,ft,tuple(int(c*ta2) for c in CREAM))
        else:
            ni=fi-hook_n; img=gf(narr_frames[min(ni,len(narr_frames)-1)])
            d=ImageDraw.Draw(img); d.text((60,170),"tick 0316",fill=MUTED,font=ftk)
            rgba=img.convert("RGBA"); ov=Image.new("RGBA",img.size,(0,0,0,0)); od=ImageDraw.Draw(ov)
            od.rounded_rectangle([W-280,165,W-170,195],radius=6,fill=ACCENT_DARK+(180,))
            od.text((W-270,168),"PROWLING",fill=DUSTY_ROSE+(255,),font=fm)
            img=Image.alpha_composite(rgba,ov).convert("RGB")
            img=pill(img,"THE CAT DOOR",100,ft,CREAM)
            for tc in tts_clips:
                p2,start,dur,text=tc
                if start<=gt<start+dur+0.3:
                    fade=min((gt-start)*4,1.0)*min((start+dur+0.3-gt)*4,1.0)
                    if fade>0.1: img=pill(img,text,H-560,fn,CREAM)
                    break
        img.save(fd/f"frame_{fi:05d}.png")

    print("  Encoding...")
    out=OUTPUT_DIR/"catdoor_episode.mp4"
    subprocess.run(["ffmpeg","-y","-framerate",str(FPS),"-i",str(fd/"frame_%05d.png"),"-i",str(ap),
        "-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart","-crf","23","-preset","slow",
        "-shortest",str(out)],capture_output=True,text=True,check=True)

    import shutil; shutil.rmtree(fd)
    if td.exists(): shutil.rmtree(td)

    sz=out.stat().st_size/1024/1024
    dur=float(subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",str(out)],capture_output=True,text=True).stdout.strip())
    print(f"\n  Output: {out}\n  {dur:.1f}s, {sz:.1f} MB\n  Done.")

if __name__=="__main__":
    main()
