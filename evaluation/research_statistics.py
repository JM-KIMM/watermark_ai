"""Small explicit paired-statistics implementation, with clustered resampling."""
import math
import random

def mean(v):return sum(v)/len(v)

def mcnemar_exact(losses,gains):
    n=losses+gains
    return min(1.,2*sum(math.comb(n,k) for k in range(min(losses,gains)+1))/2**n) if n else 1.

def holm(pvalues):
    order=sorted(range(len(pvalues)),key=pvalues.__getitem__);out=[0.]*len(order);last=0.
    for rank,i in enumerate(order):
        last=max(last,min(1.,pvalues[i]*(len(order)-rank)));out[i]=last
    return out

def paired_cluster(differences,clusters,draws=10000):
    grouped={}
    for d,c in zip(differences,clusters):grouped.setdefault(c,[]).append(d)
    groups=[grouped[k] for k in sorted(grouped)]
    rng=random.Random(20261117);values=[];extreme=0;observed=abs(sum(differences))
    for _ in range(draws):
        sampled=rng.choices(groups,k=len(groups));flat=[d for g in sampled for d in g];values.append(mean(flat))
        stat=abs(sum(sum(g)*rng.choice((-1,1)) for g in groups))
        extreme+=stat>=observed-1e-12
    values.sort()
    return dict(n=len(differences),clusters=len(groups),mean=mean(differences),ci95=[values[int(draws*.025)],values[int(draws*.975)-1]],
                sign_flip_p=(extreme+1)/(draws+1),draws=draws)

def calibration(probabilities,keys,bins=5):
    """7 categories: digits 1..6 plus residual. Keys are 1-based digit labels."""
    n=len(keys);brier=[];nll=[];bucket=[[] for _ in range(bins)]
    for p,key in zip(probabilities,keys):
        assert len(p)==7 and min(p)>=-1e-6 and abs(sum(p)-1)<1e-5
        brier.append(sum((v-(i==key-1))**2 for i,v in enumerate(p)))
        nll.append(-math.log(max(p[key-1],1e-12)))
        pred=max(range(len(p)),key=p.__getitem__);confidence=p[pred]
        bucket[min(bins-1,int(confidence*bins))].append((confidence,int(pred==key-1)))
    rows=[dict(bin=i,n=len(b),confidence=mean([x for x,y in b]) if b else None,accuracy=mean([y for x,y in b]) if b else None) for i,b in enumerate(bucket)]
    ece=sum(r['n']/n*abs(r['confidence']-r['accuracy']) for r in rows if r['n'])
    return dict(n=n,brier=mean(brier),nll=mean(nll),ece=ece,bins=rows,nll_floor=1e-12)

def jsd(a,b):
    m=[(x+y)/2 for x,y in zip(a,b)]
    return sum(x*math.log2(x/z)/2 for x,z in zip(a,m) if x>0)+sum(y*math.log2(y/z)/2 for y,z in zip(b,m) if y>0)
