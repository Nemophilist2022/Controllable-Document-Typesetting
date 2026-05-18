A heading-style or heading-numbering violation. Suggest:
- ``tool_assign_heading_styles`` to (re)apply Heading{1..4} styles
- ``tool_normalize_heading_spacing`` for space_before / space_after
- ``tool_renumber_headings`` for numbering gaps

If the rule id is ``heading.numbering.continuity`` and the document
already has Heading styles, prefer ``tool_renumber_headings`` over
re-assigning. needs_human=true when the evidence shows ambiguity
between similar headings.
