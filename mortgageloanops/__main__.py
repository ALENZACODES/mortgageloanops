import json, sys
from .pipeline import process_application
from .messaging import Messenger
from .samples import SAMPLES


def main(argv=None):
    a = (argv or sys.argv[1:]) or ["demo"]
    if a[0] == "serve":
        from .server import serve
        serve(int(a[1]) if len(a) > 1 else 8000)
    elif a[0] == "demo":
        m = Messenger()
        for name, app in SAMPLES.items():
            print(f"\n=== {name} ===")
            print(json.dumps(process_application(app, m, simulate_failures=("sms",) if name == "purchase_fthb" else ()), indent=2, default=str))
    else:
        print("usage: python -m mortgageloanops [demo | serve [port]]")


main()
