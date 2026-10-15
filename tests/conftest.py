import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("RUN_BOT", "false")
os.environ.setdefault("STAT_HTML", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "stat.html"))
