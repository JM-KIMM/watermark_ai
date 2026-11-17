"""Supplementary subject score units; never change frozen accuracy denominators."""
from collections import defaultdict

ENGLISH_THREE={24,30,32,34,37,39,41}


def score_units(rows):
    groups=defaultdict(list)
    for r in rows:
        if r['seed']!=42 or r['condition'] not in ('original','layout_control','current_choices'):continue
        exam=r['exam'];section=r['section'];q=int(r['question'])
        if exam in ('exam01','exam02','exam03','exam04'):
            units=[('questions_1_40' if q<=40 else 'questions_41_80',2.5,'100-point conversion: 40 equally weighted questions')]
        elif exam=='exam09':
            units=[(section,3 if q in ENGLISH_THREE else 2,'English reading only; listening excluded')]
        else:
            form=section.split('_')[0];part=section.split('_',1)[1]
            electives=('speech','language') if exam=='exam05' else ('probability','calculus','geometry')
            units=[(form+'_'+choice,r['weight'],'Korean common + one elective' if exam=='exam05' else 'Math objective common + one elective; short answers excluded')
                   for choice in electives if part in ('common',choice)]
        for unit,weight,note in units:groups[(exam,unit,r['condition'],note)].append((r,weight))
    result=[]
    for (exam,unit,condition,note),items in sorted(groups.items()):
        unresolved=sum(r['status'] not in ('ok','refused') for r,w in items)
        points=sum(r['correct']*w for r,w in items)
        unknown_points=sum(w for r,w in items if r['status'] not in ('ok','refused'))
        result.append(dict(exam=exam,unit=unit,condition=condition,note=note,questions=len(items),
                           correct=sum(r['correct'] for r,w in items),points=points,possible_points_range=[points,points+unknown_points],
                           max_points=sum(w for r,w in items),unresolved=unresolved))
    return result
