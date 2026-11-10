# Voice AI cost model (estimates). Rates: official pricing pages fetched 2026-11-10. See docs/12-cost-analysis.md
# scenario: (user speech min, ai speech min, turns, listen min)
S={'30s':(0.15,0.12,3,0.4),'2min':(0.7,0.7,12,1.8),'5min':(1.8,1.7,30,4.5)}
PROMPT=4000  # system prompt + tool schemas tokens
TXT_OUT=150  # text tokens out per turn (tool calls/transcript)
def gemini(u,a,t,l):
    ai_in=u*1500; ai_out=a*1500
    ctx=(ai_in+ai_out)/2*t  # accumulated audio context re-billed per turn (no caching assumed)
    return ai_in*3e-6, ai_out*12e-6, PROMPT*t*0.75e-6 + TXT_OUT*t*4.5e-6, ctx*3e-6
def oai(u,a,t,l,ain,aout,cached_a,tin,tcached,tout):
    i=u*600; o=a*1200; ctx=(i+o)/2*t
    return i*ain*1e-6, o*aout*1e-6, (PROMPT*tin+PROMPT*(t-1)*tcached+TXT_OUT*t*tout)*1e-6, ctx*cached_a*1e-6
def casc(u,a,t,l,inr=88):
    stt=l*0.5/inr        # Sarvam Rs30/hr on listen minutes (VAD-gated)
    tts=a*1000*2.0/1000/inr  # ~1000 chars/min speech, Rs2 per 1k chars (v4 flash std)
    llm=(PROMPT+800*t/2)*t*0.30e-6 + TXT_OUT*t*2.5e-6  # flash-lite text
    return stt,tts,llm,0
for name,f in [('gemini-3.8-live',gemini),('gpt-realtime-2.1-mini',lambda *x:oai(*x,10,20,0.30,0.60,0.06,2.40)),('gpt-realtime-2.1',lambda *x:oai(*x,32,64,0.40,4.00,0.40,24.00)),('cascaded sarvam+flash-lite',casc)]:
    print(name)
    for k,v in S.items():
        r=f(*v); tot=sum(r)
        print(f"  {k}: in={r[0]:.4f} out={r[1]:.4f} text={r[2]:.4f} ctx={r[3]:.4f} total=${tot:.4f} | 500=${tot*500:.0f} 1000=${tot*1000:.0f} 3000=${tot*3000:.0f}")
