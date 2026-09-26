import numpy as np, wave
HOLDS=[(3.25,.5),(5.75,.8),(10.55,.8),(16.85,.8),(20.95,.8),(27.15,.9),(30.35,.6),(38.15,.9),(45.35,.9),(51.35,.9),(56.15,.8)]
END_HOLD=2.5
TOTAL=60+sum(d for _,d in HOLDS)+END_HOLD
def F(x):  # animation time -> output time
    return x+sum(d for at,d in HOLDS if at<x)
SR=44100; D=TOTAL+1.0; N=int(SR*D); t=np.arange(N)/SR
out=np.zeros(N)
def env(n,a,r):
    e=np.ones(n); a=int(a*SR); r=int(r*SR)
    if a: e[:a]=np.linspace(0,1,a)
    if r: e[-r:]*=np.linspace(1,0,r)
    return e
def tone(f,dur,harm=6,det=0.004):
    tt=np.arange(int(dur*SR))/SR; s=np.zeros_like(tt)
    for d in (-det,0,det):
        for h in range(1,harm+1): s+=np.sin(2*np.pi*f*(1+d)*h*tt+h)/(h**1.6)
    return s/3
def add(sig,start,gain=1.0):
    i=int(start*SR); j=min(N,i+len(sig)); out[i:j]+=sig[:j-i]*gain
note=lambda m:440*2**((m-69)/12)
# pads: pain section (dark), solution (bright)
dark=[[57,60,64],[53,57,60],[57,60,64],[52,55,59],[53,57,60],[50,53,57],[52,56,59]]
for k,ch in enumerate(dark*2):
    st=k*4.0-0.2
    if st>F(27): break
    dur=min(4.6,F(27.8)-st)
    for m in ch: add(tone(note(m-12),dur,5)*env(int(dur*SR),1.2,1.4),max(st,0),0.05)
bright=[[60,64,67],[55,59,62],[57,60,64],[53,57,60]]
st=F(27.7);k=0
while st<TOTAL+.5:
    ch=bright[k%4];dur=min(4.9,TOTAL+1-st)
    for m in ch+[ch[0]+12]: add(tone(note(m-12),dur,6)*env(int(dur*SR),0.5,1.2),st,0.045)
    add(tone(note(ch[0]-24),dur,3)*env(int(dur*SR),0.3,1.0),st,0.09)
    st+=4.8;k+=1
# typewriter ticks
rng=np.random.default_rng(3)
for i in range(44):
    tc=0.35+2.1*i/44+rng.uniform(-.01,.01); n=int(.025*SR)
    add(rng.normal(0,1,n)*np.exp(-np.arange(n)/(SR*.004)),tc,0.08)
# heartbeat under stats (pain)
for b in np.arange(F(11.0),F(21.0),0.9):
    for off,g in ((0,1),(0.22,.6)):
        n=int(.25*SR);tt=np.arange(n)/SR
        add(np.sin(2*np.pi*(55-20*tt)*tt)*np.exp(-tt*18),b+off,0.35*g)
# riser into reveal + impact
n=int(2.2*SR);tt=np.arange(n)/SR;nz=rng.normal(0,1,n)
nz=np.convolve(nz,np.ones(6)/6,'same');add(nz*(tt/2.2)**2.5,F(27.75)-2.15,0.12)
n=int(2.5*SR);tt=np.arange(n)/SR
add(np.sin(2*np.pi*(90*np.exp(-tt*3)+38)*tt)*np.exp(-tt*2.2),F(27.75),0.55)
# pulse under solution: soft kick 100bpm + light hat
beat=60/100
for b in np.arange(F(30.8),F(58.4),beat):
    n=int(.35*SR);tt=np.arange(n)/SR
    add(np.sin(2*np.pi*(120*np.exp(-tt*25)+45)*tt)*np.exp(-tt*9),b,0.32)
for b in np.arange(F(38.6)+beat/2,F(58.4),beat):
    n=int(.05*SR);h=np.diff(rng.normal(0,1,n+1))*np.exp(-np.arange(n)/(SR*.01))
    add(h,b,0.025)
# whooshes at transitions
for tc in [F(x) for x in (6.2,11,21.4,30.8,38.6,45.8,51.8,56.6)]:
    n=int(.7*SR);tt=np.arange(n)/SR;nz=np.convolve(rng.normal(0,1,n),np.ones(12)/12,'same')
    add(nz*np.sin(np.pi*tt/.7)**2,tc-.45,0.10)
# final shimmer
for m in (72,76,79,84):
    add(tone(note(m),3.5,2)*np.exp(-np.arange(int(3.5*SR))/SR*.9),F(58.4),0.03)
out*=np.clip((TOTAL-t)/2.0,0,1)
out=out/np.max(np.abs(out))*0.85
st=np.stack([out,np.roll(out,int(.012*SR))*0.96],1)
w=wave.open('music.wav','wb');w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((st*32767).astype('<i2').tobytes());w.close()
print('ok')
