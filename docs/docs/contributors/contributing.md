# Contributing

## Guidelines

1. **Read documentation** - Consult `LLMs.md` and `AGENTS.md` before starting work to understand architecture and constraints
2. **Follow standards** - Adhere to coding standards, naming conventions, and security requirements
3. **Write tests** - Every new feature must include tests; update existing tests when changing code
4. **Check security** - Consider path traversal, IDOR, and input sanitization for all file operations
5. **Lint your code** - Run ruff for Python, eslint for frontend
6. **Keep it consistent** - Match existing code style and patterns

## Before submitting

- [ ] Tests pass (`make test` and frontend tests)
- [ ] Linting passes (`make ruff`, `npx eslint .` in frontend)
- [ ] Code follows naming conventions
- [ ] No bare `except Exception:`
- [ ] Frontend uses named exports
- [ ] Documentation updated if needed
- [ ] Security considerations addressed

## Project constraints

- Path length < 260 chars (Windows compatibility)
- Filename length <= 255 chars
- No reserved characters in filenames: `< > : " / \ | ? *`
- URL length ~2000 bytes limit
- All FsNode access must validate ownership/permissions
- Use `PurePosixPath` for path manipulation
- Use `FsBackend` suffix for backends, `FileSystemBackend` for local filesystem

## Getting help

- Review `LLMs.md` for project context and current goals
- Review `AGENTS.md` for detailed guidelines
- Check existing code for patterns
- Consult roadmap for planned features
