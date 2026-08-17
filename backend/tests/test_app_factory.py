import unittest


class AppFactoryTest(unittest.TestCase):
    def test_create_app_success(self):
        from app import create_app

        app = create_app()
        self.assertIsNotNone(app)
        self.assertTrue(hasattr(app, 'config'))


if __name__ == '__main__':
    unittest.main()
