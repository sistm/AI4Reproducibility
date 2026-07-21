import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, Polygon, Rectangle

# ---- palette (every colour here is documented in the legend) ----
BG,FG,DIM="#0d0d0d","#ececec","#8f8f8f"
LLM  = "#7aa7ff"   # model call
DET  = "#5fd3a0"   # deterministic, no model call
RED  = "#d76b6b"   # isolation boundary (mutual blindness)
DEP  = "#ffffff"   # data dependency: an output reused as another agent's input

# roomy canvas + generous margins so nothing touches the frame
fig,ax=plt.subplots(figsize=(30.6,16.7),dpi=300)
fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.set_xlim(0,306); ax.set_ylim(0,167); ax.axis("off")

def T(x,y,s,sz=8,c=FG,w="normal",ha="center",st="normal"):
    ax.text(x,y,s,fontsize=sz,color=c,ha=ha,va="center",weight=w,style=st,zorder=6)

def node(kind,x,y,lab,c=FG,sz=7.5,w=11,h=4.5,dash=False):
    ls="--" if dash else "-"
    if   kind=="agent":  ax.add_patch(Circle((x,y),w,facecolor=BG,edgecolor=c,lw=2.1,zorder=4,ls=ls))
    elif kind=="tool":   ax.add_patch(Polygon([(x,y+h),(x+w,y),(x,y-h),(x-w,y)],facecolor=BG,edgecolor=c,lw=1.4,zorder=4,ls=ls))
    elif kind=="check":
        k=min(3.4,w*0.26)
        ax.add_patch(Polygon([(x-w+k,y+h),(x+w-k,y+h),(x+w,y),(x+w-k,y-h),(x-w+k,y-h),(x-w,y)],facecolor=BG,edgecolor=c,lw=1.6,zorder=4,ls=ls))
    elif kind=="prompt": ax.add_patch(Rectangle((x-w,y-h),2*w,2*h,facecolor=BG,edgecolor=c,lw=1.4,zorder=4,ls=ls))
    elif kind=="asset":  ax.add_patch(Ellipse((x,y),2*w,2*h,facecolor=BG,edgecolor=c,lw=1.5,zorder=4,ls=ls))
    T(x,y,lab,sz,c,"bold" if kind=="agent" else "normal")

def arr(x1,y1,x2,y2,c=DIM,lw=1.3,dash=False,lab=None,lo=(0,2.6),lsz=6.6):
    ax.annotate("",xy=(x2,y2),xytext=(x1,y1),zorder=3,
        arrowprops=dict(arrowstyle="-|>",color=c,lw=lw,ls="--" if dash else "-",
                        shrinkA=0,shrinkB=0,mutation_scale=13))
    if lab: T((x1+x2)/2+lo[0],(y1+y2)/2+lo[1],lab,lsz,DIM)

def lane(pts,c=DIM,lw=1.1,dash=True,arrow_end=True):
    ls=(0,(4,3)) if dash else "-"
    for (ax1,ay1),(ax2,ay2) in zip(pts,pts[1:]):
        ax.plot([ax1,ax2],[ay1,ay2],color=c,lw=lw,ls=ls,zorder=2)
    if arrow_end:
        (px,py),(qx,qy)=pts[-2],pts[-1]
        ax.annotate("",xy=(qx,qy),xytext=(px,py),zorder=3,
            arrowprops=dict(arrowstyle="-|>",color=c,lw=lw,ls=ls,shrinkA=0,shrinkB=0,mutation_scale=12))

def dep_line(pts,c="#ffffff",lw=1.05):
    """Data-dependency path: thin white dashed elbows, ONE arrowhead at the end."""
    for (x1,y1),(x2,y2) in zip(pts,pts[1:]):
        ax.plot([x1,x2],[y1,y2],color=c,lw=lw,ls=(0,(4,3)),zorder=2)
    (px,py),(qx,qy)=pts[-2],pts[-1]
    ax.annotate("",xy=(qx,qy),xytext=(px,py),zorder=3,
        arrowprops=dict(arrowstyle="-|>",color=c,lw=lw,ls=(0,(4,3)),shrinkA=0,shrinkB=0,mutation_scale=10))

# ================= TITLE =================
T(153,163,"AI4Reproducibility — pipeline architecture",15,FG,"bold")
T(153,158,"KBE and CQV run as isolated subprocesses; each stage writes a "
          "schema-checked JSON that the next stage consumes",8.2,DIM)

# ================= LEGEND (two rows: shapes, then colours & lines) =========
def swatch_line(x,y,c,dash=False,arrow=False):
    ls=(0,(4,3)) if dash else "-"
    if arrow:
        # explicit dashed shaft + a solid arrowhead, so the dashed case never renders faint
        ax.plot([x-6.0,x+3.0],[y,y],color=c,lw=1.8,ls=ls,zorder=6)
        ax.annotate("",xy=(x+6.5,y),xytext=(x+3.0,y),zorder=6,
            arrowprops=dict(arrowstyle="-|>",color=c,lw=1.8,shrinkA=0,shrinkB=0,mutation_scale=14))
    else:
        ax.plot([x-5.5,x+5.5],[y,y],color=c,lw=3.0,ls=ls,zorder=6)

# row 1 — what the shapes mean (drawn neutral so shape != colour)
y1=150
shapes=[("agent","Agent (LLM)",6.5),("tool","Tool",5.0),("check","Check",5.5),
        ("prompt","Input",5.5),("asset","Output",5.5)]
x=14
for k,lab,wpad in shapes:
    node(k,x,y1,"",DIM,7,3.4 if k=="agent" else 4.2,2.4)
    T(x+6.5,y1,lab,7.6,FG,ha="left"); x+=len(lab)*1.5+18

# row 2 — what the colours and line styles mean
y2=143
colours=[(LLM,"Model call (agent / LLM check)"),(DET,"Deterministic (no model call)")]
x=14
for c,lab in colours:
    swatch_line(x,y2,c); T(x+8,y2,lab,7.6,c,ha="left"); x+=len(lab)*1.5+20
swatch_line(x,y2,RED,dash=True); T(x+8,y2,"Context isolation",7.6,RED,ha="left"); x+=17*1.5+20
swatch_line(x,y2,FG,arrow=True); T(x+8,y2,"Information flow",7.6,FG,ha="left"); x+=17*1.5+20
swatch_line(x,y2,DEP,dash=True,arrow=True)
T(x+8,y2,"Data dependency (output reused as input)",7.6,FG,ha="left")

# ================= COLUMN + BAND GEOMETRY =================
XK,XC,XE,XR = 32, 106, 180, 254
YIN, YAG, YTOOL, YCHK, YOUT = 15, 42, 68, 88, 108

def caption(x,lab,role):
    T(x,YAG-13.5,lab,7.2,DIM)
    T(x,YAG-16.3,role,6.4,DIM,st="italic")

def feed_in(node_x,node_y,agent_x,side,c=DIM):
    # elbow up the outside, then into the agent side -> keeps caption zone clear
    rim = agent_x + (11 if side>0 else -11)
    ax.plot([node_x,node_x],[node_y+4.6,YAG],color=c,lw=1.3,zorder=3)
    ax.annotate("",xy=(rim,YAG),xytext=(node_x,YAG),zorder=3,
        arrowprops=dict(arrowstyle="-|>",color=c,lw=1.3,shrinkA=0,shrinkB=0,mutation_scale=12))


# ---- isolation boundaries between the concurrent, mutually-blind agents ----
# ---- isolation boundaries: centered in the VISIBLE GAP between nearest shapes ----
# For each adjacent pair, the boundary sits midway between the right edge of the
# left column's widest structure and the left edge of the right column's widest.
_col_extents = {
    XK:(-16-10, 16+9),                 # inputs are the widest KBE structures
    XC:(-15-14.5, 16+14.5),            # the two wide check hexagons dominate CQV
    XE:(-15-11, 15+11),                # ER's two input rects (Docker left, KBE+CQV dep right)
    XR:(-19-7.0, 0+22),                # Critique (left) / final asset (right)
}
for xa,xb in [(XK,XC),(XC,XE),(XE,XR)]:
    right_edge = xa + _col_extents[xa][1]
    left_edge  = xb + _col_extents[xb][0]
    xf = (right_edge + left_edge)/2
    ax.plot([xf,xf],[9,YOUT+4],color=RED,lw=1.3,ls=(0,(3,4)),alpha=0.9,zorder=1)

# ================= KBE (stage 1a) =================
node("agent",XK,YAG,"KBE",LLM)
caption(XK,"Knowledge-Base Extraction","stage 1 · reads the paper only")
node("prompt",XK-16,YIN,"paper.pdf",FG,7.0,10,4.2)
node("prompt",XK+16,YIN,"biostat\ntemplates",FG,6.6,9,4.4)
feed_in(XK-16,YIN,XK,-1); feed_in(XK+16,YIN,XK,+1)
node("tool",XK-11,YTOOL,"pdf2text",FG,6.4,7.4,5.0)
node("tool",XK+11,YTOOL,"clean_pdf\n_text",FG,6.2,7.4,5.0)
arr(XK-4,YAG+11,XK-11,YTOOL-5.0); arr(XK+4,YAG+11,XK+11,YTOOL-5.0)
node("asset",XK,YOUT+16,"kbe_output.json\n+ notes.md",LLM,6.8,13,4.8)
arr(XK,YAG+11,XK,YOUT+16-4.8)

# ================= CQV (stage 1b) =================
node("agent",XC,YAG,"CQV",LLM)
caption(XC,"Code-Quality Verification","stage 1 · reads the code only")
node("prompt",XC-17,YIN,"code\nsupplement",FG,6.8,10,4.4)
node("prompt",XC+17,YIN,"cqv_checklist\n.yaml",FG,6.4,10.5,4.4)
feed_in(XC-17,YIN,XC,-1); feed_in(XC+17,YIN,XC,+1)

# four file tools, spaced across the tool band
tools=[("list_files",-18),("read_file",-6),("get_deps",6),("extract_zip",18)]
for lb,dx in tools:
    node("tool",XC+dx,YTOOL,lb,FG,5.8,5.4,4.2)
    arr(XC,YAG+11,XC+dx,YTOOL-4.2)

# checks band: two deterministic (green) + one model-call box (blue)
node("check",XC-15,YCHK,"static checks\nAST · regex · layout",DET,6.6,14.5,4.6)
node("check",XC+16,YCHK,"evidence rehydration\ncode context",DET,6.6,14.5,4.6)
arr(XC-5,YAG+11,XC-15,YCHK-4.6); arr(XC+5,YAG+11,XC+16,YCHK-4.6)

# stat judges — LLM, made unambiguous: blue, agent-style ring, explicit sub-label
node("check",XC,YOUT+4,"stat judges (LLM)",LLM,7.4,15,4.2)
T(XC,YOUT+9.6,"one bounded model call each",6.1,LLM,st="italic")
arr(XC,YAG+11,XC,YOUT-0.2,lab="rubric-scoped",lo=(10,0))

node("asset",XC,YOUT+16,"cqv_output.json\n+ repo_analysis.md",LLM,6.6,14,4.6)
arr(XC,YOUT+8.2,XC,YOUT+11.4)

# ================= ER (stage 2 · optional) =================
node("agent",XE,YAG,"ER",LLM)
caption(XE,"Experimental Run","stage 2 · optional · runs code in Docker")
T(XE,YAG,"ER",9.5,LLM,"bold")
T(XE,YAG-9.7,"(optional)",6.0,LLM,st="italic")
node("prompt",XE-15,YIN,"Docker image\n(GHCR, by R version)",FG,6.0,11,4.4)
feed_in(XE-15,YIN,XE,-1)
node("tool",XE-11,YTOOL,"er_preflight\n(LLM: mode)",LLM,5.8,6.6,4.2)
node("tool",XE+11,YTOOL,"er_docker\n(execute)",FG,5.8,6.6,4.2)
arr(XE-4,YAG+11,XE-11,YTOOL-4.2); arr(XE+4,YAG+11,XE+11,YTOOL-4.2)
node("check",XE,YCHK,"er_compare: pHash\n(+ LLM fig. escalation)",DET,6.5,15,4.6)
arr(XE,YAG+11,XE,YCHK-4.6)
node("asset",XE,YOUT+16,'er_output.json\nor {"status":"skipped"}',LLM,6.4,14,4.8)
arr(XE,YCHK+4.6,XE,YOUT+16-4.8)

# ================= REVIEW (stage 3) + CRITIQUE =================
node("agent",XR,YAG,"Review",LLM)
caption(XR,"Synthesis","stage 3 · reads upstream JSON only")
node("prompt",XR+15,YIN,"checklist.yaml",FG,6.4,10.5,4.4)
feed_in(XR+15,YIN,XR,+1)
node("check",XR-13,YCHK,"ER results wired\nbefore the LLM call",DET,6.2,12,4.4)
node("check",XR+13,YCHK,"coherence clamp\nverdict ↔ risk",DET,6.2,12,4.4)
arr(XR-5,YAG+11,XR-13,YCHK-4.4); arr(XR+4.2,YAG+10.2,XR+13,YCHK-4.4)

# Critique: a one-pass feedback loop INSIDE the Review stage. Its own small agent
# in the clear space right of Review, with a labeled two-arrow loop:
#   Review --(draft)--> Critique --(concerns)--> Review  (resolved once, then finalised)
cx, cy = XR+30, YAG+16
node("agent",cx,cy,"Critique",LLM,6.4,6.0,6.0)
T(cx,cy+9.6,"adversarial pass · within Review",5.4,DIM,st="italic")
# parallel loop with four EQUAL rim arcs (22.5deg): output line(90), coherence
# arrow(67.5), concerns(45), draft(22.5), checklist input(0). Directions switched.
arr(279.4,59.2, 261.8,49.8, lab="concerns", lo=(1.0,2.0), lsz=5.4)    # Critique -> Review (45deg)
arr(264.2,46.2, 278.8,54.9, lab="draft", lo=(-1.0,-2.2), lsz=5.4)     # Review -> Critique (22.5deg)

# Review's produced output (top-right)
node("asset",XR,YOUT+16,"final_review.md · exhaustive_audit_report.md\n"
     "checklist.md · risk_matrix.json",LLM,6.2,22,5.4)
arr(XR,YAG+11,XR,YOUT+16-5.4,lab="ACCEPT / MINOR / MAJOR / UNABLE_TO_ASSESS",lo=(0,10),lsz=6.0)



# ============ DATA DEPENDENCIES (white dashed = output reused as input) ============
# Symmetric perimeter loops into Review's dependency input:
#  - KBE + CQV outputs merge on the top rail, loop the LEFT side, along the bottom,
#    and up into Review's dependency input.
#  - ER's output loops the RIGHT side (mirror image), along the bottom, and merges
#    into the same Review dependency input.
d=dict(color=DEP,lw=1.1,ls=(0,(4,3)),zorder=2)
def dep_arrow(x1,y1,x2,y2):
    ax.annotate("",xy=(x2,y2),xytext=(x1,y1),zorder=3,
        arrowprops=dict(arrowstyle="-|>",color=DEP,lw=1.1,ls=(0,(4,3)),
                        shrinkA=0,shrinkB=0,mutation_scale=12))

RAIL   = 138         # top rail, raised clear ABOVE the output ellipses (tops ~129)
LEFTX  = 3           # far-left vertical (well left of paper.pdf)
RIGHTX = 302         # far-right vertical (mirror of LEFTX) for the ER loop
BOTY   = 1.5         # shared bottom rail, under the input row
MEETX  = XR-15       # x where the two bottom lines meet head-to-head, under Review input

# --- KBE + CQV outputs: MERGE at the crossing just above the KBE output ---
MERGEX = XK                                   # merge crossing sits above KBE's output
ax.plot([XK,XK],[YOUT+16+4.8,RAIL],**d)       # KBE output up toward the rail
ax.plot([XC,XC],[YOUT+16+4.6,RAIL],**d)       # CQV output up to the rail
ax.plot([XC,MERGEX+2],[RAIL,RAIL],**d)        # CQV runs left along the rail toward the crossing
dep_arrow(MERGEX+2,RAIL,MERGEX,RAIL)          # CQV arrowhead into the crossing (from the right)
dep_arrow(XK,RAIL-6,XK,RAIL)                  # KBE arrowhead pointing UP into the crossing
# merged line continues from the crossing, loops LEFT and along the bottom
ax.plot([LEFTX,MERGEX],[RAIL,RAIL],**d)       # merged line left to the far-left lane
ax.plot([LEFTX,LEFTX],[RAIL,BOTY],**d)        # down the far-left side
ax.plot([LEFTX,XE+15],[BOTY,BOTY],**d)        # along the bottom, up to ER's dep-input x (the fork)
node("prompt",XR-15,YIN,"produced outputs from\nKBE · CQV · ER agents",DEP,6.0,11,4.6)

# fork under ER: one branch rises into ER's dep input, the other continues to Review
node("prompt",XE+15,YIN,"produced outputs from\nKBE + CQV agents",DEP,6.0,11,4.6)
ax.plot([XE+15,XE+15],[BOTY,YIN-4.6],**d)     # branch UP into ER's dep input
dep_arrow(XE+15,YIN-9.2,XE+15,YIN-4.6)        # arrowhead terminating in ER's dep input
feed_in(XE+15,YIN,XE,+1,c=DEP)                # ER dep input up into ER
# KBE+CQV branch continues to its OWN vertical entry into the Review input (left side)
ax.plot([XE+15,XR-18],[BOTY,BOTY],**d)        # along the bottom to a left-of-centre riser
dep_arrow(XR-18,BOTY,XR-18,YIN-4.6)           # its own vertical arrow UP into Review's dep input

T((LEFTX+XE)/2-10,BOTY-2.4,"KBE + CQV outputs",6.4,FG,st="italic")

# --- ER output loops the RIGHT side (mirror) and enters the Review input as its
#     OWN separate vertical arrow (right side) — no merge with the KBE+CQV line ---
ax.plot([XE,XE],[YOUT+16+4.8,RAIL],**d)       # ER output up to the top rail
ax.plot([XE,RIGHTX],[RAIL,RAIL],**d)          # right to the far-right lane
ax.plot([RIGHTX,RIGHTX],[RAIL,BOTY],**d)      # down the far-right side (mirror of left)
ax.plot([XR-12,RIGHTX],[BOTY,BOTY],**d)       # along the bottom to a right-of-centre riser
dep_arrow(XR-12,BOTY,XR-12,YIN-4.6)           # its own vertical arrow UP into Review's dep input
feed_in(XR-15,YIN,XR,-1,c=DEP)                # Review dep input up into Review
T((XR+RIGHTX)/2+6,BOTY-2.4,"ER output",6.4,FG,st="italic")

plt.savefig("/home/claude/ai4re.logic.png",facecolor=BG,bbox_inches="tight",pad_inches=0.4)
plt.savefig("/home/claude/ai4re.logic.svg",facecolor=BG,bbox_inches="tight",pad_inches=0.4)
print("rendered")
