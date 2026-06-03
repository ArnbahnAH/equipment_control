


from .base import Base

PossibleDevies : list = [
]


def export(cls = None):
    """
    registers cls inside of PossibleDevies 
    """
    def decorator(cls):
        if issubclass(cls, Base):
            cls.__repr__ = lambda self: self.__class__.__name__
            PossibleDevies.append(cls)
        return cls
    if cls is None:
        return decorator

    return decorator(cls)

# example

if __name__ == "__main__":

    @export
    class Procedure(Base):
        pass

    @export
    class ProcedureB(Base):
        pass

    assert( len(PossibleDevies) == 2)
