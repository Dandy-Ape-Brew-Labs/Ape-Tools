# skill-load

The missing half of a skills ecosystem: agents can *see* what skills
exist and *load* a skill's instructions on demand, the same way
`tool-search` works for tools.

```sh
skill_load.py list                    # all skills + descriptions
skill_load.py get playwright          # frontmatter + full SKILL.md
skill_load.py get my-skill --roots ~/extra-skills
```

- A skill = a directory with `SKILL.md`; frontmatter (`---` fenced,
  `key: value`) supplies name/description — parsed leniently, no YAML
  dependency.
- Default roots: `./.devin/skills`, `./.claude/skills`,
  `./.agents/skills`, `./skills`, `~/.agents/skills`,
  `~/.claude/skills`, `~/.config/devin/skills`.
- `get` returns the absolute `path` too, so sibling files (scripts,
  references) remain discoverable relative to the skill dir.
- Read-only — never modifies skill source files.
