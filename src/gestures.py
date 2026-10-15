"""Hand pose recognition with additional practical desktop gestures."""
from math import hypot

FINGER_JOINTS = {'index':(8,6), 'middle':(12,10), 'ring':(16,14), 'pinky':(20,18)}

def distance(a,b):
    return hypot(a.x-b.x,a.y-b.y)

def get_finger_states(hand_landmarks):
    if hand_landmarks is None: return {}
    lm=getattr(hand_landmarks,'landmark',hand_landmarks)
    if len(lm)<21: return {}
    wrist=lm[0]; states={}
    for name,(tip_i,pip_i) in FINGER_JOINTS.items():
        tip_d=distance(wrist,lm[tip_i]); pip_d=distance(wrist,lm[pip_i])
        states[name]=(tip_d>pip_d*1.12 and lm[tip_i].y<lm[pip_i].y+0.035)
    palm_width=max(distance(lm[5],lm[17]),0.001)
    thumb_ratio=distance(lm[4],lm[5])/palm_width
    states['thumb']=True if thumb_ratio>=0.55 else False if thumb_ratio<=0.35 else None
    return states

def classify_gesture(hand_landmarks, handedness=None):
    states=get_finger_states(hand_landmarks)
    if not states: return 'UNKNOWN'
    lm=getattr(hand_landmarks,'landmark',hand_landmarks)
    thumb=states['thumb']
    fingers=[states['index'],states['middle'],states['ring'],states['pinky']]
    count=sum(bool(x) for x in fingers)
    # Thumb-only pose: direction differentiates COPY from PASTE.
    if count==0 and thumb is True:
        if lm[4].y < lm[3].y-0.035: return 'THUMBS_UP'
        if lm[4].y > lm[3].y+0.035: return 'THUMBS_DOWN'
        return 'UNKNOWN'
    # Index + pinky (rock sign) -> screenshot.
    if states['index'] and states['pinky'] and not states['middle'] and not states['ring']:
        return 'SCREENSHOT'
    # Thumb + index only -> Alt+Tab / switch active window.
    if states['index'] and thumb is True and not states['middle'] and not states['ring'] and not states['pinky']:
        return 'WINDOW_SWITCH'
    if count==4:
        if thumb is True: return 'OPEN_PALM'
        if thumb is False: return 'FOUR_FINGERS'
        return 'UNKNOWN'
    if count==0:
        if thumb is False: return 'FIST'
        return 'UNKNOWN'
    if count==1:
        return 'ONE_FINGER' if states['index'] else 'UNKNOWN'
    if count==2:
        if states['index'] and states['middle']: return 'TWO_FINGERS'
        return 'UNKNOWN'
    if count==3:
        return 'THREE_FINGERS'
    return 'UNKNOWN'

def get_hand_center(hand_landmarks):
    if hand_landmarks is None: return 0.5,0.5
    lm=getattr(hand_landmarks,'landmark',hand_landmarks)
    if len(lm)<21: return 0.5,0.5
    ids=(0,5,9,13,17)
    return sum(lm[i].x for i in ids)/len(ids),sum(lm[i].y for i in ids)/len(ids)
