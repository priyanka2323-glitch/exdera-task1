def test_app_module_imports():
    import app.main

    assert app.main.app.title == "Delivery Route Optimizer"
