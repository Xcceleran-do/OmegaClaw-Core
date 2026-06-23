# Skills Architecture Guide

This explains how to add new skills to the agent. **Skills are what the agent can choose to use based on user questions.**

## How skills work

1. **Agent gets a prompt** → user asks "What is AI?"
2. **Agent receives `(getSkills)` list** → all available actions
3. **Agent's LLM decides** which skill to use based on the question
4. **Agent calls skill** like `(tavily-search "what is AI")`  
5. **Skill executes** (via py-call to Python or native MeTTa)
6. **Result returned** → agent includes in response

## Current skills

From `src/skills.metta`:

| Skill | Call | What it does |
|-------|------|-------------|
| `remember` | `(remember "text")` | Store in long-term memory |
| `query` | `(query "phrase")` | Search long-term memory by embedding |
| `shell` | `(shell "command")` | Execute shell command |
| `read-file` | `(read-file "path")` | Read file contents |
| `write-file` | `(write-file "path" "text")` | Write to file |
| `send` | `(send "message")` | Send to user |
| `search` | `(search "query")` | Web search |
| `tavily-search` | `(tavily-search "query")` | Web search via Tavily API |
| `technical-analysis` | `(technical-analysis "ticker")` | Stock analysis |
| `metta` | `(metta "expr")` | Execute MeTTa/NAL logic |

## How to add a new skill

### Step 1: Implement Python function

Add to `repos/OmegaClaw-Core/src/agentverse.py` (or `helper.py`):

```python
def ai_research(topic: str, timeout: int = 60) -> str:
    """Research a topic using web search and summarize with LLM."""
    import lib_llm_ext
    
    # Step 1: Research via web search
    search_results = tavily_search(topic)
    
    # Step 2: Use LLM to summarize
    prompt = f"Summarize this research: {search_results}"
    summary = lib_llm_ext.callProvider("Bedrock", prompt, max_tokens=500)
    
    return summary
```

### Step 2: Add to skills.metta

Edit `repos/OmegaClaw-Core/src/skills.metta`:

**A) Add description in `getSkills`:**

```metta
(= (getSkills)
   (;INTERNAL:
    ...existing skills...
    ;RESEARCH:
    "- Research a topic and return summarized findings: ai-research topic"
    ...
```

**B) Add skill function definition:**

```metta
(= (ai-research $topic)
   (py-call (agentverse.ai_research $topic)))
```

### Step 3: Test

Now when user asks: **"Research what is Artificial Intelligence"**

Agent sees `ai-research` skill available, calls it:
```
(ai-research "Artificial Intelligence")
```

Result: Agent gets researched + summarized answer.

### Research-cite alias example

Because `research-cite` is an alias for the same skill, it works exactly the same way:
```
(research-cite "Artificial Intelligence")
```

That command also calls the same `agentverse.ai_research(...)` implementation, but the extra alias name makes the intention more explicit: the agent should research and cite sources.

---

## Practical example: Add `do_something` skill

This is like the scheduler `do_something` but **agent-driven** instead of periodic.

### Python (agentverse.py):

```python
def do_something(task: str) -> str:
    """Agent-requested task executor."""
    print(f"[do_something] Task: {task}")
    
    # Examples of what it could do:
    if "llm" in task.lower():
        import lib_llm_ext
        result = lib_llm_ext.callProvider("Bedrock", task, max_tokens=200)
        return f"LLM result: {result}"
    
    elif "count" in task.lower():
        # Count something, analyze data, etc.
        return f"Counted: {len(task)}"
    
    else:
        # Default: call arbitrary Python code
        return f"Task executed: {task}"
```

### MeTTa (skills.metta):

Add to `getSkills`:
```metta
"- Execute a custom task via the agent: do-something task_description"
```

Add function:
```metta
(= (do-something $task)
   (py-call (agentverse.do_something $task)))
```

### Usage

When you ask the agent:  
**"Please do-something: analyze this data"**

Agent calls:
```
(do-something "analyze this data")
```

Returns result to user.

---

## Checklist: Add a new skill

- [ ] Implement Python function in `src/agentverse.py` (or `helper.py`)
- [ ] Add description line to `getSkills` in `src/skills.metta`
- [ ] Add MeTTa function wrapper: `(= (skill-name $arg) (py-call (module.function $arg)))`
- [ ] Test: run agent, ask it something that would trigger the skill
- [ ] Check agent debug output to see if skill was called

---

## Difference: Skills vs Scheduled Jobs

| | Skills | Scheduled Jobs |
|---|--------|-----------------|

## Skill alias and collision

The new `research-cite` skill is not a conflict with `ai-research`. They are both wrappers around the same Python implementation in `agentverse.ai_research`.

This means:
- `ai-research` and `research-cite` both exist together
- they can be used interchangeably
- they do not collide unless you intentionally give them different behavior

If you want distinct behavior later, simply point one wrapper to a different Python function.

| Skill name | Implementation |
|---|---|
| `ai-research` | `agentverse.ai_research` |
| `research-cite` | `agentverse.ai_research` |


| Triggered | Agent decides based on user query | Time-based or external event |
| When used | Response to user questions | Background maintenance |
| Example | `(ai-research "topic")` → agent returns findings | Every 30s check server health |
| Architecture | Agent-driven, reactive | External-driven, proactive |

**For your use case:** Use **skills** for research, analysis, and LLM calls that respond to user input. Use **scheduler** for background tasks (health checks, periodic syncs).

---

## Next steps

I can:
1. Add `do_something` skill to the live codebase
2. Add `ai_research` skill with web search + LLM summarization
3. Show how to extend skills to call external APIs (Twitter, news, etc.)

Which would you like?
