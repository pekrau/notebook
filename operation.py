"Abstract base class for operation."


class BaseOperation:
    "Abstract base class for operation."

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

    def is_applicable(self, note):
        "Is this operation applicable to the given note?"
        return False

    def get_parameters(self, note):
        "Return the parameters required to control the operation."
        return {}

    def execute(self, note, form):
        """Execute the operation for the given note. 
        The form is a dictionary containin the required parameters;
        typically 'flask.request.form'.
        Raise ValueError if something is wrong.
        Return True if the note was changed, otherwise None.
        """
        raise NotImplementedError
