.. _update_pyluks:

=========================
Update the pyluks package
=========================
A `GitHub action <https://github.com/Laniakea-elixir-it/pyluks/blob/main/.github/workflows/python-publish.yml>`_ is
used to automatically publish new versions of pyluks in PyPI.

Once the package is successfully tested, the new version can be released with two steps:

* Create a new commit, modifying the version parameter in the `setup.cfg file <https://github.com/Laniakea-elixir-it/pyluks/blob/main/setup.cfg>`_.
  to the new version number.
* Then, tag the newly created commit (e.g. with the version number, but any tag will trigger the GitHub action).

Once the action has finished, the new version is accessible in `PyPI <https://pypi.org/project/pyluks/>`_.
