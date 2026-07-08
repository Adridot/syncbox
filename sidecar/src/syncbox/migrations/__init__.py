# Regular package (not PEP-420 namespace) so the PyInstaller freeze can import
# it and resolve the bundled .sql scripts via importlib.resources (sidecar.spec
# hiddenimports + datas). Dev behavior is unchanged.
