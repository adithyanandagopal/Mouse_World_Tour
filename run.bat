@echo off
cd /d "%~dp0"
:: pythonw has no console of its own, and `start` launches it as a fully
:: independent process -- so once this line runs, closing this window (or
:: anything else) will NOT stop Mouse World Tour. It keeps running in the
:: system tray until you Quit it from the tray icon's menu.
start "" pythonw main.py
