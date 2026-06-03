# Conductor Blog Post — Raw Material

## Approved Hook (use as opening paragraph)

"There are hundreds of videos about AI agents. People show off what they built.
Nobody explains how to actually build one or how to make it useful. That stops here."

## Meta Description (for sagheerahmed.com excerpt + social preview)

Same line — short enough to work as both.

## The Story Arc

1. The frustration: TikTok/YouTube full of AI agent demos, zero build explanations
2. What Conductor actually is: a local orchestrator you run yourself, on your own API key
3. The religion demo (the killer proof):
   - One prompt, no existing agents
   - Conductor created 5 specialists from scratch (Christianity, Islam, Judaism, Hinduism, Buddhism)
   - Called each one with a focused afterlife question
   - Synthesized a graduate-level side-by-side comparison
   - Scaffolded a project, registered a /religion skill
   - All from one session
4. How it works (brief technical):
   - AgentLibrary: YAML agent definitions
   - Conductor reads the library, picks the right specialist(s)
   - If none exists: creates one on the spot, saves permanently, uses immediately
   - Live activity panel shows every action in real time
5. Here is the code, here is how to run it, here is how to add your own agents

## Key Lines to Work In

- "I watched TikTok videos for weeks. Everyone excited about agentic AI, everyone
  showing demos. Not one video explained how to build it yourself."
- "It created five religion specialists it had never seen before, called each one,
  and produced a graduate-level comparative theology study. From one prompt."
- "The agents it creates are saved permanently. Next session they are just there."
- "You bring your own API key. It runs on your machine. Nothing goes anywhere you
  did not send it."

## Technical Points to Cover (keep brief)

- Built with Anthropic SDK + Flask + SSE streaming
- Opus 4 for routing decisions, Sonnet 4.6 for specialists (cost control)
- AgentLibrary: one YAML file per agent, two categories (Work / Personal)
- Auto-creates agents when none exist (create_agent tool)
- Saves all artifacts to timestamped output folders
- Activity panel: live right-panel showing every tool call in real time
- Prompt caching on system prompts keeps costs down

## What NOT to Include (SafeComms)

- No DEA, DOJ, sbu.dea.doj.gov
- No SPTC-SQLTOOLS-2 or any internal server names
- No internal IPs
- Reference "a large enterprise environment" if environment context is needed

## GitHub Link

https://github.com/SagheerDBA/Conductor

## Status

- [ ] Blog post drafted
- [ ] SafeComms gate passed
- [ ] Published on sagheerahmed.com
