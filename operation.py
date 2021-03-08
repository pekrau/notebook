"Abstract base class for operation."


class BaseOperation:

    def __init__(self, config):
        pass

    @property
    def name(self):
        return self.__class__.__module__

    @property
    def title(self):
        return "Short name for the operation."

    @property
    def description(self):
        return self.__class__.__doc__

    def is_relevant(self, note):
        "Is this operation relevant for the given note?"
        return False

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {}

    def execute(self, note, form):
        """Execute the operation for the given note. The form is a dictionary
        containin the required parameters; typically 'flask.request.form'.
        Raise ValueError if something is wrong.
        """
        raise NotImplementedError
