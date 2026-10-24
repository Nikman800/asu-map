#!/usr/bin/env python3
"""Line up a 3D-print STL of campus (x = east mm, y = north mm, z = up) with real coordinates.

Usage: python3 tools/fit_stl.py <model.stl> [data/osm_raw.json] [web/model.json]

Matches the model's building tops to OpenStreetMap buildings and solves scale, rotation and offset.
Start guesses come from three landmarks; if a new model moves them, edit LANDMARKS (pixel spots on a
top-down render at 5 px per mm, measured from the model's west and north edges).
Standard library only.
"""
import json, math, struct, sys
from collections import defaultdict
stl = sys.argv[1]
osm = sys.argv[2] if len(sys.argv) > 2 else "data/osm_raw.json"
out = sys.argv[3] if len(sys.argv) > 3 else "web/model.json"
b=open(stl,"rb").read(); n=struct.unpack_from("<I",b,80)[0]
# model buildings: flat top faces above the road layer, grouped by shared vertices
parent={}
def find(a):
    while parent.setdefault(a,a)!=a: parent[a]=parent[parent[a]]; a=parent[a]
    return a
tops=[]
minx,maxy=math.inf,-math.inf
for i in range(n):
    f=struct.unpack_from("<12f",b,84+50*i)[3:]
    zs=f[2::3]
    minx=min(minx,*f[0::3]); maxy=max(maxy,*f[1::3])
    if max(zs)-min(zs)<0.01 and zs[0]>2.6:
        vs=[(round(f[k],3),round(f[k+1],3),round(zs[0],2)) for k in (0,3,6)]
        tops.append(vs)
        for v in vs[1:]: parent[find(vs[0])]=find(v)
acc=defaultdict(lambda:[0,0,0,0])
for vs in tops:
    (ax,ay,_),(bx,by,_),(cx,cy,z)=vs
    a=abs((bx-ax)*(cy-ay)-(cx-ax)*(by-ay))/2
    r=acc[find(vs[0])]; r[0]+=a; r[1]+=a*(ax+bx+cx)/3; r[2]+=a*(ay+by+cy)/3; r[3]=max(r[3],z)
model=[(r[1]/r[0],r[2]/r[0],r[0],r[3]) for r in acc.values() if r[0]>0.5]
print("model buildings:",len(model))
# OSM buildings in local meters
d=json.load(open(osm))["elements"]; nodes={e["id"]:(e["lat"],e["lon"]) for e in d if e["type"]=="node"}
LAT0,LON0=33.421,-111.9325
def xy(lat,lon): return ((lon-LON0)*math.cos(math.radians(LAT0))*111320,(lat-LAT0)*110574)
O=[]
for e in d:
    if e["type"]=="way" and "building" in e.get("tags",{}):
        pts=[xy(*nodes[k]) for k in e["nodes"] if k in nodes]
        if len(pts)<3: continue
        A=cx=cy=0
        for (x1,y1),(x2,y2) in zip(pts,pts[1:]+pts[:1]):
            c=x1*y2-x2*y1; A+=c; cx+=(x1+x2)*c; cy+=(y1+y2)*c
        if abs(A)<1e-6: continue
        A/=2; O.append((cx/(6*A),cy/(6*A),abs(A),e.get("tags",{}).get("name","")))
print("osm buildings:",len(O))
def named(s): return next(o for o in O if o[3]==s)
# start: landmarks picked from the top-down render (px/5 offsets into model mm)
lm={"Desert Financial Arena":(525,400),"Grady Gammage Memorial Auditorium":(205,860)}
P=[];Q=[]
for name,(px,py) in lm.items():
    try: o=named(name)
    except StopIteration: print("missing",name); continue
    P.append((minx+px/5,maxy-py/5)); Q.append(o[:2])
def solve(P,Q):  # similarity transform model->osm: q = s*R*p + t
    n=len(P); mpx=sum(p[0] for p in P)/n; mpy=sum(p[1] for p in P)/n; mqx=sum(q[0] for q in Q)/n; mqy=sum(q[1] for q in Q)/n
    a=bb=den=0
    for (px,py),(qx,qy) in zip(P,Q):
        px-=mpx;py-=mpy;qx-=mqx;qy-=mqy
        a+=px*qx+py*qy; bb+=px*qy-py*qx; den+=px*px+py*py
    s=math.hypot(a,bb)/den; th=math.atan2(bb,a)
    c,si=s*math.cos(th),s*math.sin(th)
    return c,si,mqx-(c*mpx-si*mpy),mqy-(si*mpx+c*mpy)
T=solve(P,Q)
def apply(T,p): c,si,tx,ty=T; return (c*p[0]-si*p[1]+tx,si*p[0]+c*p[1]+ty)
for it in range(8):
    s=math.hypot(T[0],T[1])
    P=[];Q=[];err=[]
    for m in model:
        q=apply(T,m[:2]); ma=m[2]*s*s
        best=min(O,key=lambda o:(o[0]-q[0])**2+(o[1]-q[1])**2)
        dd=math.hypot(best[0]-q[0],best[1]-q[1])
        if dd<25 and 0.5<best[2]/ma<2: P.append(m[:2]);Q.append(best[:2]);err.append(dd)
    T=solve(P,Q)
    print(f"iter {it}: matched {len(P)}/{len(model)}, median error {sorted(err)[len(err)//2]:.1f} m, scale {math.hypot(T[0],T[1]):.3f} m/mm, rotation {math.degrees(math.atan2(T[1],T[0])):.2f} deg")
# express as model mm -> lat/lon at the model origin, plus scale/rotation
c,si,tx,ty=T
lat=LAT0+ty/110574; lon=LON0+tx/(math.cos(math.radians(LAT0))*111320)
json.dump({"origin_lat":lat,"origin_lon":lon,"m_per_mm":math.hypot(c,si),"rotation_deg":math.degrees(math.atan2(si,c)),
           "lat0":LAT0,"matched_buildings":len(P),"median_error_m":round(sorted(err)[len(err)//2],1)},open(out,"w"),indent=2)
print("saved",out)
