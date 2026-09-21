def format_ranges(numbers):
    """[1,2,3,5,7,8] -> '1-3, 5, 7-8'"""
    nums = sorted(set(numbers))
    if not nums:
        return ""
    parts, start, prev = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        parts.append(f"{start}-{prev}" if prev > start else f"{start}")
        start = prev = n
    parts.append(f"{start}-{prev}" if prev > start else f"{start}")
    return ", ".join(parts)
