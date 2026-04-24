# Sample Conversation

## Human (2026-01-15 10:00):

How do I reverse a list in Python?

## Claude:

Use slicing with a step of `-1`:

```python
reversed_list = my_list[::-1]
```

Or in-place with `list.reverse()`:

```python
my_list.reverse()
```

## Human (2026-01-15 10:01):

What about for a string?

## Claude:

Strings are immutable, so use slicing — same idiom:

```python
reversed_str = "hello"[::-1]
# "olleh"
```

`str.reverse()` doesn't exist.

---
