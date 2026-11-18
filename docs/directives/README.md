# Directives for friday itself

friday is developed with friday. `/friday:plan` writes directives here; `/friday:execute <id>`
runs them. Default Verify for this repo:

    uv run --with pytest pytest -q && claude plugin validate .
