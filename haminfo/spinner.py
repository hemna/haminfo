import contextlib
import random
import yaspin


class Spinner:
    enabled = True
    random = True

    random_spinners = [
        'dots', 'line', 'growVertical', 'circleHalves',
        'toggle', 'arrow3', 'bouncingBar', 'bouncingBall',
        'pong', 'shark', 'weather', 'dots12', 'moon',
    ]

    @classmethod
    def get(cls, *args, **kwargs):
        if cls.enabled:
            if len(args) < 1:  # second positional arg is text
                kwargs.setdefault("text", "Spinning up...")
            sp = yaspin.yaspin(*args, **kwargs)
            if cls.random:
                sp = getattr(sp, random.choice(cls.random_spinners))
            return sp
        else:
            return DummySpinner()

    @classmethod
    def verify_spinners_present(cls, name):
        y = yaspin.yaspin()
        for spinner in cls.random_spinners:
            if not hasattr(y, spinner):
                raise RuntimeError(
                    'Random spinner "{}" missing from yaspin'.format(spinner))


class DummySpinner:
    def __init__(self, *args, **kwargs):
        self.text = ''

    def write(self, *args, **kwargs):
        print(*args, **kwargs)

    def __getattr__(self, name):
        return self

    def __call__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        return False

    @contextlib.contextmanager
    def hidden(self):
        yield


class SpinnerProxy:
    """Spinner-like class for parallel running threads

    This class either directly sets/calls its parent's `.text` or `write()`
    if `is_current` is set or keeps the lines written around to output them
    once `is_current` is set or and outside entity uses `flush()`.

    When `prefix` is set, setting `text` on the spinner will get this
    prefix.
    """
    def __init__(self, parent_spinner, prefix=None):
        self._sp = parent_spinner
        self._prefix = prefix
        self.is_current = False

        self._lines = []
        self._text = ''

    def write(self, data):
        if self.is_current:
            self.flush()
            self._sp.write(data)
        else:
            self._lines.append(data)

    def flush(self):
        if self._lines:
            self._sp.write('\n'.join(self._lines))
            self._lines = []

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        if self.is_current:
            if self._prefix:
                self._sp.text = '{}: {}'.format(self._prefix, value)
            else:
                self._sp.text = value
        self._text = value
