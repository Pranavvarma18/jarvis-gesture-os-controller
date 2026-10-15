"""Allowlisted desktop actions for JARVIS OS gesture control."""
import os
import time
import webbrowser
import pyautogui

pyautogui.PAUSE=0.005
pyautogui.FAILSAFE=True

def adjust_volume(direction):
    if direction=='up': pyautogui.press('volumeup'); return 'Volume up'
    if direction=='down': pyautogui.press('volumedown'); return 'Volume down'
    return 'No action'

def save_screenshot():
    folder=os.path.join(os.path.expanduser('~'),'Pictures')
    os.makedirs(folder, exist_ok=True)
    path=os.path.join(folder, f'JARVIS_screenshot_{time.strftime("%Y%m%d_%H%M%S")}.png')
    pyautogui.screenshot().save(path)
    return f'Screenshot saved: {path}'

def execute_named_action(action):
    actions={
        'open_browser': lambda: (webbrowser.open('https://www.google.com'), 'Opened browser')[1],
        'play_pause': lambda: (pyautogui.press('playpause'), 'Play / pause')[1],
        'next_tab': lambda: (pyautogui.hotkey('ctrl','tab'), 'Next browser tab')[1],
        'previous_tab': lambda: (pyautogui.hotkey('ctrl','shift','tab'), 'Previous browser tab')[1],
        'browser_back': lambda: (pyautogui.hotkey('alt','left'), 'Browser back')[1],
        'browser_forward': lambda: (pyautogui.hotkey('alt','right'), 'Browser forward')[1],
        'window_switch': lambda: (pyautogui.hotkey('alt','tab'), 'Switched window')[1],
        'copy': lambda: (pyautogui.hotkey('ctrl','c'), 'Copied selection')[1],
        'paste': lambda: (pyautogui.hotkey('ctrl','v'), 'Pasted clipboard')[1],
        'screenshot': save_screenshot,
        'next_slide': lambda: (pyautogui.press('right'), 'Next slide')[1],
        'previous_slide': lambda: (pyautogui.press('left'), 'Previous slide')[1],
        'next_track': lambda: (pyautogui.press('nexttrack'), 'Next track')[1],
        'previous_track': lambda: (pyautogui.press('prevtrack'), 'Previous track')[1],
        'scroll_up': lambda: (pyautogui.scroll(4), 'Scroll up')[1],
        'scroll_down': lambda: (pyautogui.scroll(-4), 'Scroll down')[1],
        'scroll_left': lambda: (pyautogui.hscroll(-3), 'Scroll left')[1],
        'scroll_right': lambda: (pyautogui.hscroll(3), 'Scroll right')[1],
        'volume_up': lambda: adjust_volume('up'),
        'volume_down': lambda: adjust_volume('down'),
    }
    fn=actions.get(action)
    if not fn: return 'Action not allowed'
    try: return fn()
    except Exception as exc: return f'{action} failed: {exc}'

def execute_action(gesture, hand_x, hand_y):
    if gesture=='FIST': return execute_named_action('play_pause')
    if gesture=='ONE_FINGER':
        # Keep the existing scroll mapping; at extreme left/right, navigate back/forward.
        if hand_x < 0.12: return execute_named_action('browser_back')
        if hand_x > 0.88: return execute_named_action('browser_forward')
        return execute_named_action('scroll_up' if hand_y<0.5 else 'scroll_down')
    if gesture=='TWO_FINGERS':
        return execute_named_action('previous_tab' if hand_x<0.5 else 'next_tab')
    if gesture=='THREE_FINGERS': return execute_named_action('volume_up')
    if gesture=='FOUR_FINGERS': return execute_named_action('volume_down')
    if gesture=='THUMBS_UP': return execute_named_action('copy')
    if gesture=='THUMBS_DOWN': return execute_named_action('paste')
    if gesture=='SCREENSHOT': return execute_named_action('screenshot')
    if gesture=='WINDOW_SWITCH': return execute_named_action('window_switch')
    if gesture=='OPEN_PALM': return 'Neutral pose / re-arm'
    return 'No action'
