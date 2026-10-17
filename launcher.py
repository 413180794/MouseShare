"""PyInstaller entrypoint (absolute import keeps package-relative imports intact)."""
from mouseshare.app import main

raise SystemExit(main())

