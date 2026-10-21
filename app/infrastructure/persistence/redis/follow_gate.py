# Shared by P1, P2, P7 and P8 so old snapshots cannot resurrect an unfollowed author.
FOLLOW_GATE = """
local function follow_allows(recipient, author, post, score)
    if redis.call('GET', 'publication:' .. post .. ':state') == 'aborted' then return false end
    local state = redis.call('GET', 'follow:' .. recipient .. ':' .. author .. ':state')
    if not state or state == 'accepted' then
        redis.call('SADD', 'publication:' .. post .. ':recipients', recipient)
        return true
    end
    if string.sub(state, 1, 11) == 'processing:' then
        redis.call('HSET', 'follow:' .. recipient .. ':' .. author .. ':deferred', post, score)
        redis.call('SADD', 'publication:' .. post .. ':recipients', recipient)
    end
    return false
end
"""
