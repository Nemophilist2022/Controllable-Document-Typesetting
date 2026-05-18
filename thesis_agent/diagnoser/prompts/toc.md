Table-of-contents violation. Use:
- ``tool_insert_toc`` to (re)generate the TOC
- followed by ``tool_word_postprocess`` mode=full to refresh fields

If the rule id is ``toc.entry_count`` and the heading count is 0,
fix_plan should first call ``tool_assign_heading_styles`` then
``tool_insert_toc``.
