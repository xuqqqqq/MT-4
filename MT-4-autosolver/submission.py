import heapq
import itertools
import math
import random
import time
from collections import defaultdict
WILLINGNESS_VALUE = 0.0
DEFAULT_TIME_LIMIT = 5.5
LOCAL_SEARCH_TIME_FRACTION = 0.35
FAIL_PENALTY = 100.0
THREE_PAIR_PATTERNS = (((0, 1), (2, 3), (4, 5)), ((0, 1), (2, 4), (3, 5)), ((0, 1), (2, 5), (3, 4)), ((0, 2), (1, 3), (4, 5)), ((0, 2), (1, 4), (3, 5)), ((0, 2), (1, 5), (3, 4)), ((0, 3), (1, 2), (4, 5)), ((0, 3), (1, 4), (2, 5)), ((0, 3), (1, 5), (2, 4)), ((0, 4), (1, 2), (3, 5)), ((0, 4), (1, 3), (2, 5)), ((0, 4), (1, 5), (2, 3)), ((0, 5), (1, 2), (3, 4)), ((0, 5), (1, 3), (2, 4)), ((0, 5), (1, 4), (2, 3)))

def math_exp_safe(x):
    if x < -745.0:
        return 0.0
    return math.exp(x)

class Candidate(object):
    __slots__ = ('mask', 'task_str', 'courier', 'score', 'p', 'task_count')

    def __init__(self, mask, task_str, courier, score, p, task_count):
        self.mask = mask
        self.task_str = task_str
        self.courier = courier
        self.score = score
        self.p = p
        self.task_count = task_count

class ParsedProblem(object):
    __slots__ = ('task_to_idx', 'idx_to_task', 'by_mask', 'all_couriers', 'single_masks', 'pair_masks', 'all_task_mask', 'n_tasks', 'candidate_count', 'first_saving_cache', 'potential_cache', 'single_offer_value_cache', 'by_mask_courier')

    def __init__(self):
        self.task_to_idx = {}
        self.idx_to_task = []
        self.by_mask = defaultdict(list)
        self.all_couriers = []
        self.single_masks = []
        self.pair_masks = []
        self.all_task_mask = 0
        self.n_tasks = 0
        self.candidate_count = 0
        self.first_saving_cache = {}
        self.potential_cache = {}
        self.single_offer_value_cache = {}
        self.by_mask_courier = {}

class AutoSolverAgent(object):
    __slots__ = ('p', 'st', 'tb', 'deadline', 'gd', 'tm', 'bv', 'bc', 'bs', 'tried')

    def __init__(self, p):
        self.p = p
        self.st = time.time()
        self.tb = _time_budget(p)
        self.deadline = self.st + self.tb
        self.gd = self.st + max(0.06, self.tb * 0.25)
        self.tm = 'prop' if len(p.all_couriers) >= p.n_tasks else 'seq'
        self.bv = 1e+100
        self.bc = -1
        self.bs = None
        self.tried = set()

    def time_left(self):
        return self.deadline - time.time()

    def evaluate_state(self, state):
        return _state_model_value(self.p, state, self.tm)

    def _keep_if_better(self, name, state, value):
        covered = _covered_task_count(state)
        improved = value < self.bv
        if improved:
            self.bv = value
            self.bc = covered
            self.bs = state
        return improved

    def consider_groups(self, name, groups, model=None, ensure_initial=True):
        if model is None:
            model = self.tm
        groups = _groups_key(groups)
        key = (groups, model, ensure_initial)
        if key in self.tried:
            return False
        self.tried.add(key)
        state = _greedy_expected_assignment(self.p, groups, model, ensure_initial)
        return self.consider_state(name, state)

    def consider_state(self, name, state):
        value = self.evaluate_state(state)
        return self._keep_if_better(name, state, value)

class _AgentBestProxy(object):
    __slots__ = ('agent', 'pending_value')

    def __init__(self, agent):
        self.agent = agent
        self.pending_value = None

    def __getitem__(self, index):
        if index == 0:
            return self.agent.bv
        if index == 1:
            return self.agent.bs
        raise IndexError(index)

    def __setitem__(self, index, value):
        if index == 0:
            self.pending_value = value
            return
        if index == 1:
            if self.pending_value is None:
                pending_value = self.agent.evaluate_state(value)
            else:
                pending_value = self.pending_value
            covered = _covered_task_count(value)
            if pending_value < self.agent.bv:
                self.agent.bv = pending_value
                self.agent.bs = value
                self.agent.bc = covered
            self.pending_value = None
            return
        raise IndexError(index)

def _bit_count(x):
    return bin(x).count('1')

def _bits(mask):
    out = []
    idx = 0
    while mask:
        if mask & 1:
            out.append(idx)
        mask >>= 1
        idx += 1
    return out

def _parse_input(input_text):
    p = ParsedProblem()
    if not input_text:
        return p
    lines = input_text.strip().splitlines()
    if not lines:
        return p
    start = 1 if lines[0].strip().startswith('task_id_list') else 0
    best_by_key = {}
    courier_seen = set()
    for line in lines[start:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 4:
            continue
        task_str = parts[0].strip()
        courier = parts[1].strip()
        try:
            score = float(parts[2])
            willingness = float(parts[3])
        except ValueError:
            continue
        tasks = [x.strip() for x in task_str.split(',') if x.strip()]
        if not tasks or not courier:
            continue
        mask = 0
        for task in tasks:
            if task not in p.task_to_idx:
                p.task_to_idx[task] = len(p.idx_to_task)
                p.idx_to_task.append(task)
            mask |= 1 << p.task_to_idx[task]
        task_count = _bit_count(mask)
        if task_count <= 0:
            continue
        if courier not in courier_seen:
            courier_seen.add(courier)
            p.all_couriers.append(courier)
        cand = Candidate(mask, task_str, courier, score, willingness, task_count)
        key = (mask, courier)
        old = best_by_key.get(key)
        if old is None or score < old.score or (score == old.score and willingness > old.p):
            best_by_key[key] = cand
    for cand in best_by_key.values():
        p.by_mask[cand.mask].append(cand)
        p.all_task_mask |= cand.mask
    for mask in p.by_mask:
        count = _bit_count(mask)
        if count == 1:
            p.single_masks.append(mask)
        elif count == 2:
            p.pair_masks.append(mask)
    p.n_tasks = len(p.idx_to_task)
    p.all_couriers.sort()
    for mask in p.by_mask:
        p.by_mask[mask].sort(key=lambda c: (c.score, -c.p, c.courier))
        p.candidate_count += len(p.by_mask[mask])
    p.by_mask_courier = {mask: {cand.courier: cand for cand in candidates} for mask, candidates in p.by_mask.items()}
    return p

def _time_budget(p):
    candidates = p.candidate_count
    tasks = p.n_tasks
    if tasks <= 8 or candidates <= 300:
        return 0.12
    if tasks <= 20:
        return 7.2
    if candidates <= 2000:
        return 0.25
    if tasks >= 25:
        return DEFAULT_TIME_LIMIT
    if candidates <= 8000:
        return 0.45
    if candidates <= 20000:
        return 0.8
    return DEFAULT_TIME_LIMIT

def _candidate_metric(cand, alpha):
    return cand.score - alpha * cand.p * cand.task_count

def _best_metric_by_mask(p, alpha):
    best = {}
    for mask, candidates in p.by_mask.items():
        best[mask] = min((_candidate_metric(c, alpha) for c in candidates))
    return best

def _official_expected_value(p, state):
    value = 0.0
    covered = 0
    used_couriers = set()
    used_tasks = set()
    for offers in state:
        if not offers:
            continue
        offers = sorted(offers, key=lambda c: (c.score, -c.p, c.courier))
        task_ids = [t.strip() for t in offers[0].task_str.split(',')]
        if any((t in used_tasks for t in task_ids)):
            return 1e+100
        reject_prob = 1.0
        for cand in offers:
            if cand.courier in used_couriers:
                return 1e+100
            used_couriers.add(cand.courier)
            value += reject_prob * cand.p * cand.score
            reject_prob *= max(0.0, min(1.0, 1.0 - cand.p))
        value += reject_prob * FAIL_PENALTY * offers[0].task_count
        covered += offers[0].task_count
        for task_id in task_ids:
            used_tasks.add(task_id)
    value += FAIL_PENALTY * max(0, p.n_tasks - covered)
    return value

def _group_value_prop(offers, task_count):
    if not offers:
        return FAIL_PENALTY * task_count
    reject_prob = 1.0
    p_sum = 0.0
    weighted_score = 0.0
    for cand in offers:
        reject_prob *= max(0.0, min(1.0, 1.0 - cand.p))
        p_sum += cand.p
        weighted_score += cand.p * cand.score
    avg_score = weighted_score / p_sum if p_sum > 0.0 else FAIL_PENALTY * task_count
    return (1.0 - reject_prob) * avg_score + reject_prob * FAIL_PENALTY * task_count

def _prop_expected_value(p, state):
    value = 0.0
    covered = 0
    used_tasks = set()
    used_couriers = set()
    for offers in state:
        if not offers:
            continue
        task_ids = [t.strip() for t in offers[0].task_str.split(',')]
        if any((t in used_tasks for t in task_ids)):
            return 1e+100
        for cand in offers:
            if cand.courier in used_couriers:
                return 1e+100
            used_couriers.add(cand.courier)
        value += _group_value_prop(offers, offers[0].task_count)
        covered += offers[0].task_count
        for task_id in task_ids:
            used_tasks.add(task_id)
    value += FAIL_PENALTY * max(0, p.n_tasks - covered)
    return value

def _min_cost_assignment_expected(p, groups):
    group_count = len(groups)
    if group_count == 0:
        return []
    if group_count > len(p.all_couriers):
        return None
    courier_index = {}
    for courier in p.all_couriers:
        courier_index[courier] = len(courier_index)
    source = 0
    group_offset = 1
    courier_offset = group_offset + group_count
    sink = courier_offset + len(courier_index)
    node_count = sink + 1
    graph = [[] for _ in range(node_count)]

    def add_edge(u, v, cap, cost, payload):
        graph[u].append([v, cap, cost, len(graph[v]), payload])
        graph[v].append([u, 0, -cost, len(graph[u]) - 1, None])
    for i in range(group_count):
        add_edge(source, group_offset + i, 1, 0.0, None)
    for i, mask in enumerate(groups):
        candidates = p.by_mask.get(mask, [])
        if not candidates:
            return None
        task_count = _bit_count(mask)
        for cand in candidates:
            j = courier_index.get(cand.courier)
            cost = cand.p * cand.score + (1.0 - cand.p) * FAIL_PENALTY * task_count
            add_edge(group_offset + i, courier_offset + j, 1, cost, cand)
    for courier, j in courier_index.items():
        add_edge(courier_offset + j, sink, 1, 0.0, courier)
    potential = [0.0] * node_count
    flow = 0
    while flow < group_count:
        dist = [1e+100] * node_count
        parent_v = [-1] * node_count
        parent_e = [-1] * node_count
        dist[source] = 0.0
        heap = [(0.0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if d != dist[u]:
                continue
            for ei, edge in enumerate(graph[u]):
                if edge[1] <= 0:
                    continue
                v = edge[0]
                nd = d + edge[2] + potential[u] - potential[v]
                if nd + 1e-12 < dist[v]:
                    dist[v] = nd
                    parent_v[v] = u
                    parent_e[v] = ei
                    heapq.heappush(heap, (nd, v))
        if parent_v[sink] < 0:
            return None
        for i in range(node_count):
            if dist[i] < 1e+90:
                potential[i] += dist[i]
        v = sink
        while v != source:
            u = parent_v[v]
            edge = graph[u][parent_e[v]]
            edge[1] -= 1
            graph[v][edge[3]][1] += 1
            v = u
        flow += 1
    assigned = []
    for i in range(group_count):
        chosen = None
        for edge in graph[group_offset + i]:
            if edge[4] is not None and edge[1] == 0:
                chosen = edge[4]
                break
        if chosen is None:
            return None
        assigned.append(chosen)
    return assigned

def _greedy_expected_assignment(p, groups, model, ensure_initial=True):
    state = [[] for _ in groups]
    used_couriers = set()
    initial = _min_cost_assignment_expected(p, groups) if ensure_initial else None
    if ensure_initial and initial is not None:
        for i, cand in enumerate(initial):
            state[i].append(cand)
            used_couriers.add(cand.courier)
    while len(used_couriers) < len(p.all_couriers):
        best = None
        for group_index, mask in enumerate(groups):
            task_count = _bit_count(mask)
            if model == 'prop':
                current_value = _group_value_prop(state[group_index], task_count)
            else:
                current_value = _official_expected_value(p, [state[group_index]])
            for cand in p.by_mask.get(mask, []):
                if cand.courier in used_couriers:
                    continue
                trial_offers = state[group_index] + [cand]
                if model == 'prop':
                    trial_value = _group_value_prop(trial_offers, task_count)
                else:
                    trial_value = _official_expected_value(p, [trial_offers])
                saving = current_value - trial_value
                if saving <= 1e-12:
                    continue
                if best is None or saving > best[0]:
                    best = (saving, group_index, cand)
        if best is None:
            break
        _, group_index, cand = best
        state[group_index].append(cand)
        used_couriers.add(cand.courier)
    output_state = []
    for offers in state:
        if offers:
            output_state.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output_state

def _best_first_saving(p, mask):
    cached = p.first_saving_cache.get(mask)
    if cached is not None:
        return cached
    best = -1e+100
    threshold = FAIL_PENALTY * _bit_count(mask)
    for cand in p.by_mask.get(mask, []):
        saving = cand.p * (threshold - cand.score)
        if saving > best:
            best = saving
    p.first_saving_cache[mask] = best
    return best

def _make_expected_grouping(p, mode, threshold, noise, seed):
    rnd = random.Random(seed)
    single_saving = {}
    for mask in p.single_masks:
        single_saving[mask] = _best_first_saving(p, mask)
    edges = []
    for mask in p.pair_masks:
        pair_bits = _bits(mask)
        if len(pair_bits) != 2:
            continue
        left = 1 << pair_bits[0]
        right = 1 << pair_bits[1]
        pair_saving = _best_first_saving(p, mask)
        if mode == 'pair_gain':
            value = pair_saving - single_saving.get(left, 0.0) - single_saving.get(right, 0.0)
        elif mode == 'pair_raw':
            value = pair_saving
        else:
            value = pair_saving - 0.5 * (single_saving.get(left, 0.0) + single_saving.get(right, 0.0))
        if noise:
            value += (rnd.random() - 0.5) * noise
        edges.append((value, mask))
    edges.sort(reverse=True)
    used = 0
    groups = []
    for value, mask in edges:
        if used & mask:
            continue
        if value >= threshold:
            groups.append(mask)
            used |= mask
    for i in range(p.n_tasks):
        mask = 1 << i
        if not used & mask and mask in p.by_mask:
            groups.append(mask)
            used |= mask
    return _groups_key(groups)

def _make_forced_pair_grouping(p):
    pair_scores = []
    for mask in p.pair_masks:
        pair_bits = _bits(mask)
        if len(pair_bits) != 2:
            continue
        pair_scores.append((_best_first_saving(p, mask), mask))
    pair_scores.sort(reverse=True)
    used = 0
    groups = []
    for _, mask in pair_scores:
        if used & mask:
            continue
        groups.append(mask)
        used |= mask
    for i in range(p.n_tasks):
        mask = 1 << i
        if not used & mask and mask in p.by_mask:
            groups.append(mask)
            used |= mask
    return _groups_key(groups)

def _multi_offer_potential(p, mask, top_k):
    key = (mask, top_k)
    cached = p.potential_cache.get(key)
    if cached is not None:
        return cached
    values = []
    threshold = FAIL_PENALTY * _bit_count(mask)
    for cand in p.by_mask.get(mask, []):
        saving = cand.p * (threshold - cand.score)
        if saving > 0.0:
            values.append(saving)
    values.sort(reverse=True)
    total = sum(values[:top_k])
    p.potential_cache[key] = total
    return total

def _best_single_offer_value(p, mask):
    cached = p.single_offer_value_cache.get(mask)
    if cached is not None:
        return cached
    best = 1e+100
    task_count = _bit_count(mask)
    for cand in p.by_mask.get(mask, []):
        value = cand.p * cand.score + (1.0 - cand.p) * FAIL_PENALTY * task_count
        if value < best:
            best = value
    p.single_offer_value_cache[mask] = best
    return best

def _matching_edge_value(p, mask, mode, top_k):
    if mode == 'expected':
        task_count = _bit_count(mask)
        bv = _best_single_offer_value(p, mask)
        if bv >= 1e+90:
            return -1e+100
        return FAIL_PENALTY * task_count - bv
    if mode == 'potential_gain':
        pair_bits = _bits(mask)
        if len(pair_bits) != 2:
            return -1e+100
        left = 1 << pair_bits[0]
        right = 1 << pair_bits[1]
        return _multi_offer_potential(p, mask, top_k) - _multi_offer_potential(p, left, top_k) - _multi_offer_potential(p, right, top_k)
    if mode == 'potential_half':
        pair_bits = _bits(mask)
        if len(pair_bits) != 2:
            return -1e+100
        left = 1 << pair_bits[0]
        right = 1 << pair_bits[1]
        return _multi_offer_potential(p, mask, top_k) - 0.5 * (_multi_offer_potential(p, left, top_k) + _multi_offer_potential(p, right, top_k))
    return _multi_offer_potential(p, mask, top_k)

def _make_matching_grouping(p, mode, top_k, threshold, noise, seed, three_opt=False):
    rnd = random.Random(seed)
    edge_value = {}
    edges = []
    for mask in p.pair_masks:
        pair_bits = _bits(mask)
        if len(pair_bits) != 2:
            continue
        value = _matching_edge_value(p, mask, mode, top_k)
        edge_value[mask] = value
        noisy_value = value + ((rnd.random() - 0.5) * noise if noise else 0.0)
        edges.append((noisy_value, value, pair_bits[0], pair_bits[1], mask))
    edges.sort(reverse=True)
    mate = [-1] * p.n_tasks
    for noisy_value, value, left, right, mask in edges:
        if value < threshold:
            continue
        if mate[left] < 0 and mate[right] < 0:
            mate[left] = right
            mate[right] = left
    improved = True
    while improved:
        improved = False
        pairs = []
        seen = set()
        for i in range(p.n_tasks):
            j = mate[i]
            if j >= 0 and i not in seen and (j not in seen):
                pairs.append((min(i, j), max(i, j)))
                seen.add(i)
                seen.add(j)
        for a_idx in range(len(pairs)):
            if improved:
                break
            a, b = pairs[a_idx]
            old_one = 1 << a | 1 << b
            for c_idx in range(a_idx + 1, len(pairs)):
                c, d = pairs[c_idx]
                old_two = 1 << c | 1 << d
                old_value = edge_value.get(old_one, -1e+100) + edge_value.get(old_two, -1e+100)
                alt_one = 1 << a | 1 << c
                alt_two = 1 << b | 1 << d
                alt_value = edge_value.get(alt_one, -1e+100) + edge_value.get(alt_two, -1e+100)
                if alt_value > old_value + 1e-09:
                    mate[a] = c
                    mate[c] = a
                    mate[b] = d
                    mate[d] = b
                    improved = True
                    break
                alt_one = 1 << a | 1 << d
                alt_two = 1 << b | 1 << c
                alt_value = edge_value.get(alt_one, -1e+100) + edge_value.get(alt_two, -1e+100)
                if alt_value > old_value + 1e-09:
                    mate[a] = d
                    mate[d] = a
                    mate[b] = c
                    mate[c] = b
                    improved = True
                    break
    if three_opt and p.n_tasks <= 32:
        improved = True
        while improved:
            improved = False
            pairs = []
            seen = set()
            for i in range(p.n_tasks):
                j = mate[i]
                if j >= 0 and i not in seen and (j not in seen):
                    pairs.append((min(i, j), max(i, j)))
                    seen.add(i)
                    seen.add(j)
            for first in range(len(pairs)):
                if improved:
                    break
                for second in range(first + 1, len(pairs)):
                    if improved:
                        break
                    for third in range(second + 1, len(pairs)):
                        selected = (pairs[first], pairs[second], pairs[third])
                        nodes = [selected[0][0], selected[0][1], selected[1][0], selected[1][1], selected[2][0], selected[2][1]]
                        old_value = 0.0
                        for a, b in selected:
                            old_value += edge_value.get(1 << a | 1 << b, -1e+100)
                        bv = old_value
                        best_pairs = None
                        for pattern in THREE_PAIR_PATTERNS:
                            trial_value = 0.0
                            trial_pairs = []
                            valid = True
                            for left_pos, right_pos in pattern:
                                a = nodes[left_pos]
                                b = nodes[right_pos]
                                value = edge_value.get(1 << a | 1 << b, -1e+100)
                                if value <= -1e+90:
                                    valid = False
                                    break
                                trial_value += value
                                trial_pairs.append((a, b))
                            if valid and trial_value > bv + 1e-09:
                                bv = trial_value
                                best_pairs = trial_pairs
                        if best_pairs is not None:
                            for a, b in selected:
                                mate[a] = -1
                                mate[b] = -1
                            for a, b in best_pairs:
                                mate[a] = b
                                mate[b] = a
                            improved = True
                            break
    groups = []
    used = 0
    for i in range(p.n_tasks):
        if used & 1 << i:
            continue
        j = mate[i]
        if j >= 0:
            mask = 1 << i | 1 << j
            groups.append(mask)
            used |= mask
        else:
            mask = 1 << i
            if mask in p.by_mask:
                groups.append(mask)
                used |= mask
    return _groups_key(groups)

def _make_overlap_grouping(p, top_k, weight, threshold, noise, seed):
    sv = {}
    st = {}
    for mask in p.single_masks:
        vals = {}
        ranked = []
        for cand in p.by_mask.get(mask, []):
            value = cand.p * (FAIL_PENALTY * cand.task_count - cand.score)
            if value > 0.0:
                vals[cand.courier] = value
                ranked.append((value, cand.courier))
        ranked.sort(reverse=True)
        sv[mask] = vals
        st[mask] = set(courier for _, courier in ranked[:top_k])
    shared = {}
    for mask in p.pair_masks:
        bits = _bits(mask)
        if len(bits) != 2:
            continue
        left = 1 << bits[0]
        right = 1 << bits[1]
        lv = sv.get(left, {})
        rv = sv.get(right, {})
        if not lv or not rv:
            continue
        value = len(st.get(left, set()) & st.get(right, set())) * FAIL_PENALTY * 0.03
        for cand in p.by_mask.get(mask, []):
            a = lv.get(cand.courier)
            b = rv.get(cand.courier)
            if a is None or b is None:
                continue
            pair_value = cand.p * (FAIL_PENALTY * cand.task_count - cand.score)
            if pair_value > 0.0:
                value += min(a, b, pair_value)
        if value > 0.0:
            shared[mask] = value
    rnd = random.Random(seed)
    edge_value = {}
    edges = []
    for mask in p.pair_masks:
        bits = _bits(mask)
        if len(bits) != 2:
            continue
        value = _matching_edge_value(p, mask, 'potential_half', top_k) + weight * shared.get(mask, 0.0)
        edge_value[mask] = value
        noisy = value + ((rnd.random() - 0.5) * noise if noise else 0.0)
        edges.append((noisy, value, bits[0], bits[1], mask))
    edges.sort(reverse=True)
    mate = [-1] * p.n_tasks
    for _, value, left, right, mask in edges:
        if value < threshold:
            continue
        if mate[left] < 0 and mate[right] < 0:
            mate[left] = right
            mate[right] = left
    improved = True
    while improved:
        improved = False
        pairs = []
        seen = set()
        for i in range(p.n_tasks):
            j = mate[i]
            if j >= 0 and i not in seen and (j not in seen):
                pairs.append((min(i, j), max(i, j)))
                seen.add(i)
                seen.add(j)
        for a_idx in range(len(pairs)):
            if improved:
                break
            a, b = pairs[a_idx]
            old_one = 1 << a | 1 << b
            for c_idx in range(a_idx + 1, len(pairs)):
                c, d = pairs[c_idx]
                old_two = 1 << c | 1 << d
                old_value = edge_value.get(old_one, -1e+100) + edge_value.get(old_two, -1e+100)
                alt_one = 1 << a | 1 << c
                alt_two = 1 << b | 1 << d
                alt_value = edge_value.get(alt_one, -1e+100) + edge_value.get(alt_two, -1e+100)
                if alt_value > old_value + 1e-09:
                    mate[a] = c
                    mate[c] = a
                    mate[b] = d
                    mate[d] = b
                    improved = True
                    break
                alt_one = 1 << a | 1 << d
                alt_two = 1 << b | 1 << c
                alt_value = edge_value.get(alt_one, -1e+100) + edge_value.get(alt_two, -1e+100)
                if alt_value > old_value + 1e-09:
                    mate[a] = d
                    mate[d] = a
                    mate[b] = c
                    mate[c] = b
                    improved = True
                    break
    groups = []
    used = 0
    for i in range(p.n_tasks):
        j = mate[i]
        if j > i:
            mask = 1 << i | 1 << j
            if mask in p.by_mask:
                groups.append(mask)
                used |= mask
    for i in range(p.n_tasks):
        mask = 1 << i
        if not used & mask and mask in p.by_mask:
            groups.append(mask)
            used |= mask
    return _groups_key(groups)

def _candidate_saving_assignment(p):
    rows = []
    for mask, candidates in p.by_mask.items():
        task_count = _bit_count(mask)
        threshold = FAIL_PENALTY * task_count
        for cand in candidates:
            saving = cand.p * (threshold - cand.score)
            if saving > 0.0:
                rows.append((saving, mask, cand))
    rows.sort(reverse=True, key=lambda x: (x[0], x[2].p, -x[2].score))
    used_tasks = 0
    used_couriers = set()
    state = []
    for _, mask, cand in rows:
        if used_tasks & mask:
            continue
        if cand.courier in used_couriers:
            continue
        state.append([cand])
        used_tasks |= mask
        used_couriers.add(cand.courier)
    return state

def _local_replace_sparse(p, state, deadline):
    current = [list(offers) for offers in state if offers]
    current_value = _prop_expected_value(p, current)
    rows = []
    for mask, candidates in p.by_mask.items():
        for cand in candidates:
            saving = cand.p * (FAIL_PENALTY * _bit_count(mask) - cand.score)
            rows.append((saving, mask, cand))
    rows.sort(reverse=True, key=lambda x: (x[0], x[2].p, -x[2].score))
    while time.time() < deadline:
        improved = False
        for remove_index in range(len(current)):
            if time.time() >= deadline:
                break
            base = []
            base_tasks = 0
            base_couriers = set()
            for i, offers in enumerate(current):
                if i == remove_index:
                    continue
                base.append(list(offers))
                base_tasks |= offers[0].mask
                for cand in offers:
                    base_couriers.add(cand.courier)
            for _, mask, cand in rows:
                if base_tasks & mask:
                    continue
                if cand.courier in base_couriers:
                    continue
                trial = base + [[cand]]
                trial_value = _prop_expected_value(p, trial)
                if trial_value + 1e-09 < current_value:
                    current = trial
                    current_value = trial_value
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return current

def _local_replace_sparse_pair(p, state, deadline):
    current = [list(offers) for offers in state if offers]
    current_value = _prop_expected_value(p, current)
    rows = []
    for mask, candidates in p.by_mask.items():
        for cand in candidates:
            saving = cand.p * (FAIL_PENALTY * _bit_count(mask) - cand.score)
            if saving > 0.0:
                rows.append((saving, mask, cand))
    rows.sort(reverse=True, key=lambda x: (x[0], x[2].p, -x[2].score))
    while time.time() < deadline:
        improved = False
        n = len(current)
        for first in range(n):
            if improved or time.time() >= deadline:
                break
            for second in range(first + 1, n):
                if time.time() >= deadline:
                    break
                base = []
                base_tasks = 0
                base_couriers = set()
                for idx, offers in enumerate(current):
                    if idx == first or idx == second:
                        continue
                    base.append(list(offers))
                    base_tasks |= offers[0].mask
                    for cand in offers:
                        base_couriers.add(cand.courier)
                available = []
                for _, mask, cand in rows:
                    if base_tasks & mask:
                        continue
                    if cand.courier in base_couriers:
                        continue
                    available.append((mask, cand))
                    if len(available) >= 90:
                        break
                best_trial = None
                bv = current_value
                for i in range(len(available)):
                    mask1, cand1 = available[i]
                    trial = base + [[cand1]]
                    trial_value = _prop_expected_value(p, trial)
                    if trial_value + 1e-09 < bv:
                        bv = trial_value
                        best_trial = trial
                    for j in range(i + 1, len(available)):
                        mask2, cand2 = available[j]
                        if mask1 & mask2:
                            continue
                        if cand1.courier == cand2.courier:
                            continue
                        trial = base + [[cand1], [cand2]]
                        trial_value = _prop_expected_value(p, trial)
                        if trial_value + 1e-09 < bv:
                            bv = trial_value
                            best_trial = trial
                if best_trial is not None:
                    current = best_trial
                    current_value = bv
                    improved = True
                    break
        if not improved:
            break
    return current

def _repair_sparse_uncovered_lns(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if not current:
        return current

    def covered_mask(st):
        out = 0
        for offers in st:
            if offers:
                out |= offers[0].mask
        return out
    missing = p.all_task_mask & ~covered_mask(current)
    if not missing:
        return current
    current_value = _state_model_value(p, current, model)
    bs = current
    bv = current_value
    miss_masks = [mask for mask in p.by_mask if mask & missing]
    ranked = []
    for idx, offers in enumerate(current):
        best = 1e+100
        for cand in offers:
            for mask in miss_masks:
                item = p.by_mask_courier.get(mask, {}).get(cand.courier)
                if item is None:
                    continue
                task_count = _bit_count(mask)
                value = item.p * item.score + (1.0 - item.p) * FAIL_PENALTY * task_count
                if value < best:
                    best = value
        ranked.append((best, idx))
    ranked.sort()
    ids = [idx for _, idx in ranked[:min(16, len(ranked))]]
    for remove_count in (1, 2, 3, 4):
        if time.time() >= deadline:
            break
        for combo in itertools.combinations(ids, remove_count):
            if time.time() >= deadline:
                break
            combo_set = set(combo)
            released_mask = missing
            local_couriers = []
            base = []
            for idx, offers in enumerate(current):
                if idx in combo_set:
                    released_mask |= offers[0].mask
                    for cand in offers:
                        if cand.courier not in local_couriers:
                            local_couriers.append(cand.courier)
                else:
                    base.append(list(offers))
            if _bit_count(released_mask) > 9:
                continue
            alternatives = _enumerate_partitions(p, released_mask)
            alternatives.sort(key=lambda groups: (len(groups), groups))
            checked = 0
            for groups in alternatives:
                if time.time() >= deadline:
                    break
                if len(groups) > len(local_couriers):
                    continue
                local_state = _restricted_expected_assignment(p, list(groups), local_couriers, model)
                covered = 0
                for offers in local_state:
                    if offers:
                        covered += offers[0].task_count
                if covered != _bit_count(released_mask):
                    continue
                trial = base + local_state
                value = _state_model_value(p, trial, model)
                checked += 1
                if value + 1e-09 < bv:
                    bv = value
                    bs = trial
                if checked >= 600:
                    break
    return bs

def _covered_mask(state):
    out = 0
    if not state:
        return out
    for offers in state:
        if offers:
            out |= offers[0].mask
    return out

def _covered_task_count(state):
    return _bit_count(_covered_mask(state))

def _state_model_value(p, state, model):
    if model == 'prop':
        return _prop_expected_value(p, state)
    return _official_expected_value(p, state)

def _local_improve_expected(p, state, deadline, model):
    if not state:
        return state
    current = [list(offers) for offers in state]
    current_value = _state_model_value(p, current, model)
    by_key = {}
    for offers in current:
        if not offers:
            continue
        mask = offers[0].mask
        for cand in p.by_mask.get(mask, []):
            by_key[mask, cand.courier] = cand
    while time.time() < deadline:
        improved = False
        for from_index in range(len(current)):
            if time.time() >= deadline or improved:
                break
            if len(current[from_index]) <= 1:
                continue
            moving_offers = list(current[from_index])
            for cand in moving_offers:
                if improved:
                    break
                for to_index in range(len(current)):
                    if time.time() >= deadline:
                        break
                    if from_index == to_index:
                        continue
                    target_mask = current[to_index][0].mask
                    replacement = by_key.get((target_mask, cand.courier))
                    if replacement is None:
                        continue
                    if any((x.courier == cand.courier for x in current[to_index])):
                        continue
                    trial = [list(offers) for offers in current]
                    trial[from_index] = [x for x in trial[from_index] if x.courier != cand.courier]
                    trial[to_index].append(replacement)
                    trial_value = _state_model_value(p, trial, model)
                    if trial_value + 1e-09 < current_value:
                        current = trial
                        current_value = trial_value
                        improved = True
                        break
        if improved:
            continue
        for left_index in range(len(current)):
            if time.time() >= deadline or improved:
                break
            for right_index in range(left_index + 1, len(current)):
                if time.time() >= deadline or improved:
                    break
                left_mask = current[left_index][0].mask
                right_mask = current[right_index][0].mask
                left_offers = list(current[left_index])
                right_offers = list(current[right_index])
                for left_cand in left_offers:
                    if improved:
                        break
                    for right_cand in right_offers:
                        if time.time() >= deadline:
                            break
                        new_left = by_key.get((left_mask, right_cand.courier))
                        new_right = by_key.get((right_mask, left_cand.courier))
                        if new_left is None or new_right is None:
                            continue
                        trial = [list(offers) for offers in current]
                        trial[left_index] = [new_left if x.courier == left_cand.courier else x for x in trial[left_index]]
                        trial[right_index] = [new_right if x.courier == right_cand.courier else x for x in trial[right_index]]
                        trial_value = _state_model_value(p, trial, model)
                        if trial_value + 1e-09 < current_value:
                            current = trial
                            current_value = trial_value
                            improved = True
                            break
        if not improved:
            break
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_subset_reassign_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if model != 'prop' or len(current) < 3:
        return current
    if p.n_tasks < 25 or p.n_tasks > 45:
        return current
    if len(p.all_couriers) < p.n_tasks:
        return current
    by_key = {}
    for mask, candidates in p.by_mask.items():
        if _bit_count(mask) != 1:
            continue
        for cand in candidates:
            by_key[mask, cand.courier] = cand

    def group_value(offers):
        return _group_value_prop(offers, offers[0].task_count)

    def best_reassign(selected):
        if time.time() >= deadline:
            return None
        masks = [current[idx][0].mask for idx in selected]
        for mask in masks:
            if _bit_count(mask) != 1:
                return None
        courier_ids = []
        seen = set()
        for idx in selected:
            for cand in current[idx]:
                if cand.courier not in seen:
                    seen.add(cand.courier)
                    courier_ids.append(cand.courier)
        group_count = len(selected)
        courier_count = len(courier_ids)
        if courier_count < group_count or courier_count > 9:
            return None
        old_value = 0.0
        for idx in selected:
            old_value += group_value(current[idx])
        full = (1 << courier_count) - 1
        subset_values = []
        subset_offers = []
        for mask in masks:
            candidates = []
            for courier_id in courier_ids:
                cand = by_key.get((mask, courier_id))
                if cand is None:
                    return None
                candidates.append(cand)
            values = [0.0] * (1 << courier_count)
            offers_cache = [None] * (1 << courier_count)
            for subset in range(1, 1 << courier_count):
                offers = []
                for bit in range(courier_count):
                    if subset & 1 << bit:
                        offers.append(candidates[bit])
                values[subset] = group_value(offers)
                offers_cache[subset] = offers
            subset_values.append(values)
            subset_offers.append(offers_cache)
        bv = old_value
        best_sets = None
        for first in range(1, full):
            if time.time() >= deadline:
                break
            rest = full ^ first
            second = rest
            while second:
                third = rest ^ second
                if third:
                    value = subset_values[0][first] + subset_values[1][second] + subset_values[2][third]
                    if value + 1e-09 < bv:
                        bv = value
                        best_sets = (first, second, third)
                second = second - 1 & rest
        if best_sets is None:
            return None
        groups = []
        for group_index, subset in enumerate(best_sets):
            groups.append(list(subset_offers[group_index][subset]))
        return (old_value - bv, groups)

    def evaluate_triples(triples):
        best = None
        for selected in triples:
            if time.time() >= deadline:
                break
            result = best_reassign(selected)
            if result is None:
                continue
            gain, groups = result
            if gain > 1e-09 and (best is None or gain > best[0]):
                best = (gain, selected, groups)
        return best
    changed_indices = []
    move_count = 0
    while time.time() < deadline and move_count < 5:
        values = []
        for idx in range(len(current)):
            values.append((group_value(current[idx]), idx))
        order = [idx for _, idx in sorted(values, reverse=True)]
        if changed_indices:
            triple_set = set()
            for changed in changed_indices:
                for left_pos in range(len(order)):
                    left = order[left_pos]
                    if left == changed:
                        continue
                    for right_pos in range(left_pos + 1, len(order)):
                        right = order[right_pos]
                        if right == changed:
                            continue
                        triple_set.add(tuple(sorted((changed, left, right))))
            triples = list(triple_set)
            triples.sort(key=lambda item: -(group_value(current[item[0]]) + group_value(current[item[1]]) + group_value(current[item[2]])))
            best = evaluate_triples(triples)
        else:
            selected_order = order[:min(12, len(order))]
            triples = []
            for a in range(len(selected_order)):
                for b in range(a + 1, len(selected_order)):
                    for c in range(b + 1, len(selected_order)):
                        triples.append((selected_order[a], selected_order[b], selected_order[c]))
            best = evaluate_triples(triples)
            if best is None and time.time() < deadline:
                selected_order = order[:min(15, len(order))]
                triples = []
                for a in range(len(selected_order)):
                    for b in range(a + 1, len(selected_order)):
                        for c in range(b + 1, len(selected_order)):
                            triples.append((selected_order[a], selected_order[b], selected_order[c]))
                best = evaluate_triples(triples)
        if best is None:
            break
        _, selected, groups = best
        for pos, idx in enumerate(selected):
            current[idx] = groups[pos]
        changed_indices = list(selected)
        move_count += 1
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _anneal_single_task_reassign(p, state, deadline, seed, max_iters):
    current = [list(offers) for offers in state if offers]
    if len(current) < 8:
        return current
    if len(p.all_couriers) < p.n_tasks:
        return current
    task_counts = []
    for offers in current:
        if not offers:
            return current
        task_counts.append(_bit_count(offers[0].mask))
    by_key = {}
    for mask, candidates in p.by_mask.items():
        for cand in candidates:
            by_key[mask, cand.courier] = cand
    masks = [offers[0].mask for offers in current]
    penalty = 103.0

    def value_from_stats(reject_prob, p_sum, weighted_score, task_count):
        if p_sum <= 1e-15:
            return penalty * task_count
        return (1.0 - reject_prob) * (weighted_score / p_sum) + reject_prob * penalty * task_count
    reject_probs = []
    p_sums = []
    weighted_scores = []
    values = []
    for offers in current:
        reject_prob = 1.0
        p_sum = 0.0
        weighted_score = 0.0
        for cand in offers:
            reject_prob *= max(0.0, min(1.0, 1.0 - cand.p))
            p_sum += cand.p
            weighted_score += cand.p * cand.score
        reject_probs.append(reject_prob)
        p_sums.append(p_sum)
        weighted_scores.append(weighted_score)
        values.append(value_from_stats(reject_prob, p_sum, weighted_score, task_counts[len(values)]))
    current_value = sum(values)
    bv = current_value
    bs = [list(offers) for offers in current]
    rnd = random.Random(seed)
    group_count = len(current)
    movable = []
    for idx, offers in enumerate(current):
        if len(offers) > 1:
            movable.append(idx)
    temp0 = 2.0
    move_probability = 0.55
    min_temp = 0.003
    for iteration in range(max_iters):
        if iteration & 4095 == 0 and time.time() >= deadline:
            break
        if rnd.random() < move_probability:
            if not movable:
                continue
            left = movable[rnd.randrange(len(movable))]
            if len(current[left]) <= 1:
                continue
            right = rnd.randrange(group_count - 1)
            if right >= left:
                right += 1
            pos = rnd.randrange(len(current[left]))
            moving = current[left][pos]
            right_offer = by_key.get((masks[right], moving.courier))
            if right_offer is None:
                continue
            left_keep_prob = max(0.0, min(1.0, 1.0 - moving.p))
            if left_keep_prob <= 1e-15:
                continue
            right_keep_prob = max(0.0, min(1.0, 1.0 - right_offer.p))
            new_left_reject = reject_probs[left] / left_keep_prob
            new_left_p_sum = p_sums[left] - moving.p
            new_left_weighted = weighted_scores[left] - moving.p * moving.score
            new_left_value = value_from_stats(new_left_reject, new_left_p_sum, new_left_weighted, task_counts[left])
            new_right_reject = reject_probs[right] * right_keep_prob
            new_right_p_sum = p_sums[right] + right_offer.p
            new_right_weighted = weighted_scores[right] + right_offer.p * right_offer.score
            new_right_value = value_from_stats(new_right_reject, new_right_p_sum, new_right_weighted, task_counts[right])
            delta = new_left_value + new_right_value - values[left] - values[right]
            temperature = max(min_temp, temp0 * (1.0 - float(iteration) / max_iters))
            if delta < 0.0 or rnd.random() < math_exp_safe(-delta / temperature):
                left_offers = current[left][:pos] + current[left][pos + 1:]
                right_offers = current[right] + [right_offer]
                current[left] = left_offers
                current[right] = right_offers
                reject_probs[left] = new_left_reject
                reject_probs[right] = new_right_reject
                p_sums[left] = new_left_p_sum
                p_sums[right] = new_right_p_sum
                weighted_scores[left] = new_left_weighted
                weighted_scores[right] = new_right_weighted
                values[left] = new_left_value
                values[right] = new_right_value
                current_value += delta
                if len(left_offers) == 1:
                    try:
                        movable.remove(left)
                    except ValueError:
                        pass
                if len(right_offers) == 2:
                    movable.append(right)
                if current_value < bv:
                    bv = current_value
                    bs = [list(offers) for offers in current]
        else:
            left = rnd.randrange(group_count - 1)
            right = rnd.randrange(group_count - 1)
            if right >= left:
                right += 1
            left_pos = rnd.randrange(len(current[left]))
            right_pos = rnd.randrange(len(current[right]))
            left_cand = current[left][left_pos]
            right_cand = current[right][right_pos]
            new_left = by_key.get((masks[left], right_cand.courier))
            new_right = by_key.get((masks[right], left_cand.courier))
            if new_left is None or new_right is None:
                continue
            left_old_keep = max(0.0, min(1.0, 1.0 - left_cand.p))
            right_old_keep = max(0.0, min(1.0, 1.0 - right_cand.p))
            if left_old_keep <= 1e-15 or right_old_keep <= 1e-15:
                continue
            left_new_keep = max(0.0, min(1.0, 1.0 - new_left.p))
            right_new_keep = max(0.0, min(1.0, 1.0 - new_right.p))
            new_left_reject = reject_probs[left] / left_old_keep * left_new_keep
            new_left_p_sum = p_sums[left] - left_cand.p + new_left.p
            new_left_weighted = weighted_scores[left] - left_cand.p * left_cand.score + new_left.p * new_left.score
            new_left_value = value_from_stats(new_left_reject, new_left_p_sum, new_left_weighted, task_counts[left])
            new_right_reject = reject_probs[right] / right_old_keep * right_new_keep
            new_right_p_sum = p_sums[right] - right_cand.p + new_right.p
            new_right_weighted = weighted_scores[right] - right_cand.p * right_cand.score + new_right.p * new_right.score
            new_right_value = value_from_stats(new_right_reject, new_right_p_sum, new_right_weighted, task_counts[right])
            delta = new_left_value + new_right_value - values[left] - values[right]
            temperature = max(min_temp, temp0 * (1.0 - float(iteration) / max_iters))
            if delta < 0.0 or rnd.random() < math_exp_safe(-delta / temperature):
                left_offers = list(current[left])
                right_offers = list(current[right])
                left_offers[left_pos] = new_left
                right_offers[right_pos] = new_right
                current[left] = left_offers
                current[right] = right_offers
                reject_probs[left] = new_left_reject
                reject_probs[right] = new_right_reject
                p_sums[left] = new_left_p_sum
                p_sums[right] = new_right_p_sum
                weighted_scores[left] = new_left_weighted
                weighted_scores[right] = new_right_weighted
                values[left] = new_left_value
                values[right] = new_right_value
                current_value += delta
                if current_value < bv:
                    bv = current_value
                    bs = [list(offers) for offers in current]
    output = []
    for offers in bs:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_mask_subset_reassign_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if model != 'prop' or len(current) < 3:
        return current
    if p.n_tasks < 25 or p.n_tasks > 32:
        return current
    by_key = {}
    for mask, candidates in p.by_mask.items():
        for cand in candidates:
            by_key[mask, cand.courier] = cand

    def group_value(offers):
        return _group_value_prop(offers, offers[0].task_count)

    def best_reassign(selected):
        if time.time() >= deadline:
            return None
        masks = [current[idx][0].mask for idx in selected]
        courier_ids = []
        seen = set()
        for idx in selected:
            for cand in current[idx]:
                if cand.courier not in seen:
                    seen.add(cand.courier)
                    courier_ids.append(cand.courier)
        group_count = len(selected)
        courier_count = len(courier_ids)
        if courier_count < group_count or courier_count > 9:
            return None
        full = (1 << courier_count) - 1
        old_value = 0.0
        for idx in selected:
            old_value += group_value(current[idx])
        subset_values = []
        subset_offers = []
        for mask in masks:
            candidates = []
            for courier_id in courier_ids:
                cand = by_key.get((mask, courier_id))
                if cand is None:
                    return None
                candidates.append(cand)
            values = [0.0] * (1 << courier_count)
            offers_cache = [None] * (1 << courier_count)
            for subset in range(1, 1 << courier_count):
                offers = []
                for bit in range(courier_count):
                    if subset & 1 << bit:
                        offers.append(candidates[bit])
                values[subset] = group_value(offers)
                offers_cache[subset] = offers
            subset_values.append(values)
            subset_offers.append(offers_cache)
        bv = old_value
        best_sets = None
        if group_count == 2:
            for first in range(1, full):
                second = full ^ first
                if not second:
                    continue
                value = subset_values[0][first] + subset_values[1][second]
                if value + 1e-09 < bv:
                    bv = value
                    best_sets = (first, second)
        else:
            for first in range(1, full):
                if time.time() >= deadline:
                    break
                rest = full ^ first
                second = rest
                while second:
                    third = rest ^ second
                    if third:
                        value = subset_values[0][first] + subset_values[1][second] + subset_values[2][third]
                        if value + 1e-09 < bv:
                            bv = value
                            best_sets = (first, second, third)
                    second = second - 1 & rest
        if best_sets is None:
            return None
        groups = []
        for group_index, subset in enumerate(best_sets):
            groups.append(list(subset_offers[group_index][subset]))
        return (old_value - bv, groups)
    move_count = 0
    while time.time() < deadline and move_count < 5:
        values = []
        for idx in range(len(current)):
            values.append((group_value(current[idx]), idx))
        order = [idx for _, idx in sorted(values, reverse=True)]
        order = order[:min(18, len(order))]
        best = None
        for group_count in (3, 2):
            if time.time() >= deadline or best is not None:
                break
            for a in range(len(order)):
                if time.time() >= deadline:
                    break
                for b in range(a + 1, len(order)):
                    if time.time() >= deadline:
                        break
                    if group_count == 2:
                        selected = (order[a], order[b])
                        result = best_reassign(selected)
                        if result is not None and result[0] > 1e-09:
                            if best is None or result[0] > best[0]:
                                best = (result[0], selected, result[1])
                        continue
                    for c in range(b + 1, len(order)):
                        if time.time() >= deadline:
                            break
                        selected = (order[a], order[b], order[c])
                        result = best_reassign(selected)
                        if result is not None and result[0] > 1e-09:
                            if best is None or result[0] > best[0]:
                                best = (result[0], selected, result[1])
        if best is None:
            break
        _, selected, groups = best
        for pos, idx in enumerate(selected):
            current[idx] = groups[pos]
        move_count += 1
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_pair_subset_reassign_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if model != 'prop' or len(current) < 2:
        return current
    if p.n_tasks > 20:
        return current
    by_key = {}
    for mask, candidates in p.by_mask.items():
        if _bit_count(mask) != 1:
            continue
        for cand in candidates:
            by_key[mask, cand.courier] = cand

    def group_value(offers):
        return _group_value_prop(offers, offers[0].task_count)
    move_count = 0
    while time.time() < deadline and move_count < 10:
        values = []
        for idx in range(len(current)):
            values.append((group_value(current[idx]), idx))
        order = [idx for _, idx in sorted(values, reverse=True)]
        best = None
        for left_pos in range(len(order)):
            if time.time() >= deadline:
                break
            left_index = order[left_pos]
            left_mask = current[left_index][0].mask
            if _bit_count(left_mask) != 1:
                continue
            for right_pos in range(left_pos + 1, len(order)):
                if time.time() >= deadline:
                    break
                right_index = order[right_pos]
                right_mask = current[right_index][0].mask
                if _bit_count(right_mask) != 1:
                    continue
                courier_ids = []
                seen = set()
                for cand in current[left_index] + current[right_index]:
                    if cand.courier not in seen:
                        seen.add(cand.courier)
                        courier_ids.append(cand.courier)
                courier_count = len(courier_ids)
                if courier_count < 2 or courier_count > 18:
                    continue
                left_candidates = []
                right_candidates = []
                ok = True
                for courier_id in courier_ids:
                    left_cand = by_key.get((left_mask, courier_id))
                    right_cand = by_key.get((right_mask, courier_id))
                    if left_cand is None or right_cand is None:
                        ok = False
                        break
                    left_candidates.append(left_cand)
                    right_candidates.append(right_cand)
                if not ok:
                    continue
                old_value = group_value(current[left_index]) + group_value(current[right_index])
                full = (1 << courier_count) - 1
                left_values = [0.0] * (1 << courier_count)
                right_values = [0.0] * (1 << courier_count)
                left_offers = [None] * (1 << courier_count)
                right_offers = [None] * (1 << courier_count)
                for subset in range(1, 1 << courier_count):
                    offers = []
                    for bit in range(courier_count):
                        if subset & 1 << bit:
                            offers.append(left_candidates[bit])
                    left_values[subset] = group_value(offers)
                    left_offers[subset] = offers
                    offers = []
                    for bit in range(courier_count):
                        if subset & 1 << bit:
                            offers.append(right_candidates[bit])
                    right_values[subset] = group_value(offers)
                    right_offers[subset] = offers
                subset = 1
                while subset < full:
                    other = full ^ subset
                    if other:
                        value = left_values[subset] + right_values[other]
                        gain = old_value - value
                        if gain > 1e-09 and (best is None or gain > best[0]):
                            best = (gain, left_index, right_index, left_offers[subset], right_offers[other])
                    subset += 1
        if best is None:
            break
        _, left_index, right_index, left_offers, right_offers = best
        current[left_index] = list(left_offers)
        current[right_index] = list(right_offers)
        move_count += 1
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_triple_subset_reassign_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if model != 'prop' or len(current) < 3:
        return current
    if p.n_tasks < 9 or p.n_tasks > 18:
        return current
    by_key = {}
    for mask, candidates in p.by_mask.items():
        if _bit_count(mask) != 1:
            continue
        for cand in candidates:
            by_key[mask, cand.courier] = cand

    def group_value(offers):
        return _group_value_prop(offers, offers[0].task_count)
    move_count = 0
    while time.time() < deadline and move_count < 3:
        values = []
        for idx in range(len(current)):
            values.append((group_value(current[idx]), idx))
        order = [idx for _, idx in sorted(values, reverse=True)]
        order = order[:min(16, len(order))]
        best = None
        for a_pos in range(len(order)):
            if time.time() >= deadline:
                break
            for b_pos in range(a_pos + 1, len(order)):
                if time.time() >= deadline:
                    break
                for c_pos in range(b_pos + 1, len(order)):
                    if time.time() >= deadline:
                        break
                    selected = (order[a_pos], order[b_pos], order[c_pos])
                    masks = [current[idx][0].mask for idx in selected]
                    if any((_bit_count(mask) != 1 for mask in masks)):
                        continue
                    courier_ids = []
                    seen = set()
                    for idx in selected:
                        for cand in current[idx]:
                            if cand.courier not in seen:
                                seen.add(cand.courier)
                                courier_ids.append(cand.courier)
                    courier_count = len(courier_ids)
                    if courier_count < 3 or courier_count > 13:
                        continue
                    candidates_by_group = []
                    ok = True
                    for mask in masks:
                        group_candidates = []
                        for courier_id in courier_ids:
                            cand = by_key.get((mask, courier_id))
                            if cand is None:
                                ok = False
                                break
                            group_candidates.append(cand)
                        if not ok:
                            break
                        candidates_by_group.append(group_candidates)
                    if not ok:
                        continue
                    old_value = 0.0
                    for idx in selected:
                        old_value += group_value(current[idx])
                    full = (1 << courier_count) - 1
                    subset_values = []
                    subset_offers = []
                    for group_index in range(3):
                        values_cache = [0.0] * (1 << courier_count)
                        offers_cache = [None] * (1 << courier_count)
                        for subset in range(1, 1 << courier_count):
                            offers = []
                            group_candidates = candidates_by_group[group_index]
                            for bit in range(courier_count):
                                if subset & 1 << bit:
                                    offers.append(group_candidates[bit])
                            values_cache[subset] = group_value(offers)
                            offers_cache[subset] = offers
                        subset_values.append(values_cache)
                        subset_offers.append(offers_cache)
                    first = 1
                    while first < full:
                        rest = full ^ first
                        second = rest
                        while second:
                            third = rest ^ second
                            if third:
                                value = subset_values[0][first] + subset_values[1][second] + subset_values[2][third]
                                gain = old_value - value
                                if gain > 1e-09 and (best is None or gain > best[0]):
                                    best = (gain, selected, (subset_offers[0][first], subset_offers[1][second], subset_offers[2][third]))
                            second = second - 1 & rest
                        first += 1
        if best is None:
            break
        _, selected, groups = best
        for pos, idx in enumerate(selected):
            current[idx] = list(groups[pos])
        move_count += 1
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _restricted_expected_assignment(p, groups, courier_ids, model):
    state = [[] for _ in groups]
    used_couriers = set()
    courier_set = set(courier_ids)
    while len(used_couriers) < len(courier_set):
        best = None
        for group_index, mask in enumerate(groups):
            task_count = _bit_count(mask)
            if model == 'prop':
                current_value = _group_value_prop(state[group_index], task_count)
            else:
                current_value = _official_expected_value(p, [state[group_index]])
            for courier_id in courier_set:
                if courier_id in used_couriers:
                    continue
                cand = p.by_mask_courier.get(mask, {}).get(courier_id)
                if cand is None:
                    continue
                trial_offers = state[group_index] + [cand]
                if model == 'prop':
                    trial_value = _group_value_prop(trial_offers, task_count)
                else:
                    trial_value = _official_expected_value(p, [trial_offers])
                saving = current_value - trial_value
                if saving <= 1e-12:
                    continue
                if best is None or saving > best[0]:
                    best = (saving, group_index, cand)
        if best is None:
            break
        _, group_index, cand = best
        state[group_index].append(cand)
        used_couriers.add(cand.courier)
    output = []
    for offers in state:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_repartition_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if len(current) < 2:
        return current
    current_value = _state_model_value(p, current, model)
    rnd = random.Random(20260516)
    while time.time() < deadline:
        improved = False
        pairs = []
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                pairs.append((i, j))
        rnd.shuffle(pairs)
        for left_index, right_index in pairs:
            if time.time() >= deadline:
                break
            left = current[left_index]
            right = current[right_index]
            if not left or not right:
                continue
            union_mask = left[0].mask | right[0].mask
            if _bit_count(union_mask) > 4:
                continue
            local_couriers = []
            for cand in left + right:
                if cand.courier not in local_couriers:
                    local_couriers.append(cand.courier)
            old_groups = _groups_key([left[0].mask, right[0].mask])
            alternatives = _enumerate_partitions(p, union_mask)
            alternatives.sort(key=lambda x: (len(x), x))
            base = []
            for idx, offers in enumerate(current):
                if idx != left_index and idx != right_index:
                    base.append(list(offers))
            for alt_groups in alternatives:
                if alt_groups == old_groups:
                    continue
                local_state = _restricted_expected_assignment(p, list(alt_groups), local_couriers, model)
                trial = base + local_state
                trial_value = _state_model_value(p, trial, model)
                if trial_value + 1e-09 < current_value:
                    current = trial
                    current_value = trial_value
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_repartition_three_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if len(current) < 3 or p.n_tasks > 35:
        return current
    current_value = _state_model_value(p, current, model)
    rnd = random.Random(20260517)
    while time.time() < deadline:
        improved = False
        triples = []
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                for k in range(j + 1, len(current)):
                    triples.append((i, j, k))
        rnd.shuffle(triples)
        for left_index, mid_index, right_index in triples[:3500]:
            if time.time() >= deadline:
                break
            selected = (left_index, mid_index, right_index)
            union_mask = 0
            local_couriers = []
            old_groups = []
            for idx in selected:
                offers = current[idx]
                if not offers:
                    continue
                union_mask |= offers[0].mask
                old_groups.append(offers[0].mask)
                for cand in offers:
                    if cand.courier not in local_couriers:
                        local_couriers.append(cand.courier)
            if len(old_groups) != 3 or _bit_count(union_mask) > 6:
                continue
            alternatives = _enumerate_partitions(p, union_mask)
            alternatives.sort(key=lambda x: (len(x), x))
            old_key = _groups_key(old_groups)
            base = []
            selected_set = set(selected)
            for idx, offers in enumerate(current):
                if idx not in selected_set:
                    base.append(list(offers))
            for alt_groups in alternatives:
                if alt_groups == old_key:
                    continue
                local_state = _restricted_expected_assignment(p, list(alt_groups), local_couriers, model)
                trial = base + local_state
                trial_value = _state_model_value(p, trial, model)
                if trial_value + 1e-09 < current_value:
                    current = trial
                    current_value = trial_value
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _local_repartition_four_expected(p, state, deadline, model):
    current = [list(offers) for offers in state if offers]
    if len(current) < 4 or p.n_tasks > 35:
        return current
    current_value = _state_model_value(p, current, model)
    rnd = random.Random(20260519)
    while time.time() < deadline:
        improved = False
        quads = []
        for a in range(len(current)):
            for b in range(a + 1, len(current)):
                for c in range(b + 1, len(current)):
                    for d in range(c + 1, len(current)):
                        quads.append((a, b, c, d))
        rnd.shuffle(quads)
        for selected in quads[:1400]:
            if time.time() >= deadline:
                break
            union_mask = 0
            local_couriers = []
            old_groups = []
            for idx in selected:
                offers = current[idx]
                if not offers:
                    continue
                union_mask |= offers[0].mask
                old_groups.append(offers[0].mask)
                for cand in offers:
                    if cand.courier not in local_couriers:
                        local_couriers.append(cand.courier)
            if len(old_groups) != 4 or _bit_count(union_mask) > 8:
                continue
            alternatives = _enumerate_partitions(p, union_mask)
            alternatives.sort(key=lambda x: (len(x), x))
            old_key = _groups_key(old_groups)
            selected_set = set(selected)
            base = []
            for idx, offers in enumerate(current):
                if idx not in selected_set:
                    base.append(list(offers))
            for alt_groups in alternatives:
                if alt_groups == old_key:
                    continue
                local_state = _restricted_expected_assignment(p, list(alt_groups), local_couriers, model)
                trial = base + local_state
                trial_value = _state_model_value(p, trial, model)
                if trial_value + 1e-09 < current_value:
                    current = trial
                    current_value = trial_value
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    output = []
    for offers in current:
        if offers:
            output.append(sorted(offers, key=lambda c: (c.score, -c.p, c.courier)))
    return output

def _state_to_output(state):
    assigned_couriers = set()
    assigned_tasks = set()
    result = []
    if not state:
        return result
    for offers in state:
        if not offers:
            continue
        offers = sorted(offers, key=lambda c: (c.score, -c.p, c.courier))
        task_id_list_str = offers[0].task_str
        task_ids = [t.strip() for t in task_id_list_str.split(',')]
        if any((t in assigned_tasks for t in task_ids)):
            continue
        courier_ids = []
        for cand in offers:
            courier_id = cand.courier
            if courier_id in assigned_couriers:
                continue
            assigned_couriers.add(courier_id)
            courier_ids.append(courier_id)
        if not courier_ids:
            continue
        for t in task_ids:
            assigned_tasks.add(t)
        result.append((task_id_list_str, courier_ids))
    return result

def _groups_key(groups):
    return tuple(sorted(groups))

def _all_single_grouping(p):
    groups = []
    for i in range(p.n_tasks):
        mask = 1 << i
        if mask in p.by_mask:
            groups.append(mask)
    return _groups_key(groups)

def _make_greedy_grouping(p, alpha, threshold, noise, seed):
    best = _best_metric_by_mask(p, alpha)
    rnd = random.Random(seed)
    edges = []
    for mask in p.pair_masks:
        pair_bits = _bits(mask)
        if len(pair_bits) != 2:
            continue
        a = 1 << pair_bits[0]
        b = 1 << pair_bits[1]
        if a not in best or b not in best:
            continue
        saving = best[a] + best[b] - best[mask]
        noisy_value = saving
        if noise:
            noisy_value += (rnd.random() - 0.5) * noise
        edges.append((noisy_value, saving, mask))
    edges.sort(reverse=True)
    used = 0
    groups = []
    for _, saving, mask in edges:
        if used & mask:
            continue
        if saving > threshold:
            groups.append(mask)
            used |= mask
    for i in range(p.n_tasks):
        mask = 1 << i
        if not used & mask and mask in p.by_mask:
            groups.append(mask)
            used |= mask
    return _groups_key(groups)

def _enumerate_partitions(p, mask):
    bit_list = _bits(mask)
    result = []

    def rec(remaining, current):
        if not remaining:
            result.append(_groups_key(current))
            return
        first = remaining[0]
        single = 1 << first
        if single in p.by_mask:
            rec(remaining[1:], current + [single])
        for k in range(1, len(remaining)):
            second = remaining[k]
            pair = 1 << first | 1 << second
            if pair in p.by_mask:
                rec(remaining[1:k] + remaining[k + 1:], current + [pair])
    rec(bit_list, [])
    return result

def solve(input_text: str) -> list:
    global FAIL_PENALTY
    p = _parse_input(input_text)
    if p.n_tasks == 0:
        return []
    agent = AutoSolverAgent(p)
    st = agent.st
    tb = agent.tb
    deadline = agent.deadline
    gd = agent.gd
    best = _AgentBestProxy(agent)
    tried = agent.tried
    tm = agent.tm
    avg_willingness = 0.0
    willingness_count = 0
    score_sum = 0.0
    score_sq_sum = 0.0
    for candidates in p.by_mask.values():
        for cand in candidates:
            avg_willingness += cand.p
            score_sum += cand.score
            score_sq_sum += cand.score * cand.score
            willingness_count += 1
    if willingness_count:
        avg_willingness /= willingness_count
    avg_score = score_sum / willingness_count if willingness_count else 0.0
    score_std = math.sqrt(max(0.0, score_sq_sum / willingness_count - avg_score * avg_score)) if willingness_count else 0.0
    original_fail_penalty = FAIL_PENALTY
    if p.n_tasks >= 25 and p.n_tasks <= 32 and (len(p.all_couriers) >= p.n_tasks) and (avg_willingness < 0.071):
        FAIL_PENALTY = 110.0

    def consider(groups, model=None, ensure_initial=True):
        if model is None:
            model = tm
        return agent.consider_groups('group:%s' % model, groups, model, ensure_initial)

    def consider_state(state):
        return agent.consider_state('state', state)

    consider(_all_single_grouping(p))
    forced_pair_groups = _make_forced_pair_grouping(p)
    consider(forced_pair_groups, tm)
    scarce_couriers = len(p.all_couriers) <= p.n_tasks * 1.35
    low_willingness = avg_willingness < 0.35
    very_low_willingness = avg_willingness < 0.28
    extreme_low_willingness = avg_willingness < 0.18
    seed = 17
    if scarce_couriers or low_willingness:
        consider(forced_pair_groups, 'seq')
        consider(forced_pair_groups, 'seq', False)
    if scarce_couriers:
        sparse_state = _candidate_saving_assignment(p)
        if time.time() < deadline:
            sparse_deadline = min(deadline, st + max(0.05, tb * 0.22))
            sparse_state = _local_replace_sparse(p, sparse_state, sparse_deadline)
        if p.n_tasks >= 35 and len(p.all_couriers) <= max(24, int(p.n_tasks * 0.65)):
            sparse_pair_deadline = min(st + 3.15, time.time() + 2.35)
            sparse_state = _local_replace_sparse_pair(p, sparse_state, sparse_pair_deadline)
        consider_state(sparse_state)
        if p.n_tasks >= 35 and len(p.all_couriers) <= max(24, int(p.n_tasks * 0.65)) and (time.time() < deadline):
            saved_fail_penalty = FAIL_PENALTY
            for alt_fail_penalty in (108.0, 120.0):
                if time.time() >= deadline:
                    break
                FAIL_PENALTY = alt_fail_penalty
                p.first_saving_cache.clear()
                p.potential_cache.clear()
                p.single_offer_value_cache.clear()
                alt_sparse_state = _candidate_saving_assignment(p)
                alt_sparse_state = _local_replace_sparse_pair(p, alt_sparse_state, min(deadline, time.time() + 0.28))
                FAIL_PENALTY = saved_fail_penalty
                p.first_saving_cache.clear()
                p.potential_cache.clear()
                p.single_offer_value_cache.clear()
                consider_state(alt_sparse_state)
    if tm == 'prop' and (not extreme_low_willingness) and p.n_tasks >= 25 and p.n_tasks <= 45 and len(p.all_couriers) >= max(p.n_tasks, 70):
        overlap_configs = ((4, 0.3, 15.0, 20.0), (3, 0.3, -10.0, 20.0), (4, 0.5, 30.0, 20.0), (5, 0.15, -40.0, 20.0))
        for top_k, weight, threshold, noise in overlap_configs:
            if time.time() >= gd:
                break
            groups = _make_overlap_grouping(p, top_k, weight, threshold, noise, seed)
            consider(groups, 'prop', False)
            seed += 17
    if low_willingness and p.n_tasks >= 25 and (p.n_tasks <= 32) and (len(p.all_couriers) >= p.n_tasks):
        matching_configs = (('potential_half', 3, -80.0, 'prop', False), ('potential_raw', 3, -80.0, 'prop', False), ('potential_gain', 3, -80.0, 'prop', False), ('potential_half', 4, -80.0, 'prop', False), ('potential_raw', 4, -80.0, 'prop', False), ('potential_gain', 4, -80.0, 'prop', False), ('potential_half', 5, -80.0, 'prop', False), ('potential_gain', 5, -80.0, 'seq', False), ('potential_half', 4, 25.0, 'seq', False), ('potential_gain', 5, -120.0, 'prop', False), ('potential_gain', 5, -80.0, 'prop', False), ('potential_gain', 3, -40.0, 'prop', False))
        for mode, top_k, threshold, model, ensure_initial in matching_configs:
            if time.time() >= deadline:
                break
            groups = _make_matching_grouping(p, mode, top_k, threshold, 0.0, seed, True)
            consider(groups, model, ensure_initial)
            seed += 13
        if extreme_low_willingness:
            randomized_matching_configs = (('potential_half', 3, 20.0, 50.0, 151), ('potential_half', 3, 20.0, 90.0, 151), ('potential_half', 3, 20.0, 140.0, 29), ('potential_half', 3, 20.0, 25.0, 151), ('potential_half', 3, 20.0, 25.0, 97), ('potential_half', 3, 40.0, 140.0, 29))
            for mode, top_k, threshold, noise, match_seed in randomized_matching_configs:
                if time.time() >= deadline:
                    break
                groups = _make_matching_grouping(p, mode, top_k, threshold, noise, match_seed, True)
                consider(groups, 'prop', False)
        if (not very_low_willingness) and score_std <= 20.5 and time.time() < gd:
            saved_penalty = FAIL_PENALTY
            for alt_penalty, mode, top_k, threshold in ((85.0, 'potential_half', 4, -120.0), (130.0, 'potential_gain', 5, -160.0)):
                if time.time() >= gd:
                    break
                FAIL_PENALTY = alt_penalty
                p.first_saving_cache.clear()
                p.potential_cache.clear()
                p.single_offer_value_cache.clear()
                groups = _make_matching_grouping(p, mode, top_k, threshold, 0.0, seed, True)
                state = _greedy_expected_assignment(p, groups, 'prop', False)
                FAIL_PENALTY = saved_penalty
                p.first_saving_cache.clear()
                p.potential_cache.clear()
                p.single_offer_value_cache.clear()
                consider_state(state)
                seed += 11
            FAIL_PENALTY = saved_penalty
            p.first_saving_cache.clear()
            p.potential_cache.clear()
            p.single_offer_value_cache.clear()
    modes = ('pair_raw', 'pair_half', 'pair_gain')
    thresholds = (-220.0, -140.0, -80.0, -40.0, -10.0, 0.0, 10.0, 25.0, 40.0, 60.0)
    noises = (0.0, 2.0, 6.0, 12.0, 24.0)
    for mode in modes:
        for threshold in thresholds:
            if time.time() >= gd:
                break
            consider(_make_expected_grouping(p, mode, threshold, 0.0, seed))
            if len(p.all_couriers) <= p.n_tasks * 1.25:
                consider(_make_expected_grouping(p, mode, threshold, 0.0, seed), 'seq', False)
            seed += 19
        if time.time() >= gd:
            break
    for alpha in (0.0, 0.5, 1.0, 2.0, -1.0):
        if time.time() >= gd:
            break
        consider(_make_greedy_grouping(p, alpha, 0.0, 0.0, seed))
        seed += 23
    while time.time() < gd:
        for mode in modes:
            for threshold in thresholds:
                for noise in noises:
                    if time.time() >= gd:
                        break
                    groups = _make_expected_grouping(p, mode, threshold, noise, seed)
                    consider(groups)
                    if len(p.all_couriers) <= p.n_tasks * 1.25:
                        consider(groups, 'seq', False)
                    seed += 31
                if time.time() >= gd:
                    break
            if time.time() >= gd:
                break
    if best[1] is None:
        FAIL_PENALTY = original_fail_penalty
        return []
    if time.time() < deadline:
        repartition_deadline = st + min(tb, max(tb * 0.7, tb - 0.75))
        improved_state = _local_repartition_expected(p, best[1], min(deadline, repartition_deadline), tm)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
    tail_repartition = p.n_tasks <= 35 and len(p.all_couriers) >= p.n_tasks
    deep_tail_repartition = tail_repartition and (tb > 1.0 or p.n_tasks <= 20)
    single_offer_refine = tm == 'prop' and p.n_tasks >= 25 and (p.n_tasks <= 45) and (len(p.all_couriers) >= p.n_tasks) and (not very_low_willingness)
    mask_offer_refine = tm == 'prop' and p.n_tasks >= 25 and (p.n_tasks <= 32) and (len(p.all_couriers) >= p.n_tasks)
    large_single_refine = single_offer_refine and p.n_tasks >= 36
    large_anneal_refine = large_single_refine and avg_willingness <= 0.34
    if time.time() < deadline:
        improve_deadline = deadline
        if deep_tail_repartition and deadline - time.time() > 1.2:
            improve_deadline = deadline - 1.2
        if large_single_refine and deadline - time.time() > 2.1:
            improve_deadline = min(improve_deadline, deadline - 2.1)
        elif single_offer_refine and deadline - time.time() > 0.8:
            improve_deadline = min(improve_deadline, deadline - 0.8)
        if mask_offer_refine and deadline - time.time() > 1.1:
            improve_deadline = min(improve_deadline, deadline - 1.1)
        improved_state = _local_improve_expected(p, best[1], improve_deadline, tm)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
    if mask_offer_refine and time.time() < deadline:
        improved_state = _local_mask_subset_reassign_expected(p, best[1], min(deadline, time.time() + 0.95), tm)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
    if scarce_couriers and p.n_tasks >= 35 and (time.time() < deadline):
        sparse_pair_deadline = min(deadline, time.time() + 2.5)
        improved_state = _local_replace_sparse_pair(p, best[1], sparse_pair_deadline)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
        if time.time() < deadline:
            improved_state = _repair_sparse_uncovered_lns(p, best[1], min(deadline, time.time() + 1.15), tm)
            improved_value = _state_model_value(p, improved_state, tm)
            if improved_value < best[0]:
                best[0] = improved_value
                best[1] = improved_state
    if single_offer_refine and (not large_anneal_refine) and (time.time() < deadline):
        if large_single_refine:
            refine_deadline = min(st + 8.65, time.time() + 5.2)
        else:
            refine_deadline = min(deadline, time.time() + 0.55)
        improved_state = _local_subset_reassign_expected(p, best[1], refine_deadline, tm)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
            if time.time() < deadline:
                improved_state = _local_improve_expected(p, best[1], min(deadline, time.time() + 0.25), tm)
                improved_value = _state_model_value(p, improved_state, tm)
                if improved_value < best[0]:
                    best[0] = improved_value
                    best[1] = improved_state
    if tm == 'prop' and p.n_tasks >= 25 and (p.n_tasks <= 45) and (len(p.all_couriers) >= p.n_tasks) and (not very_low_willingness):
        if p.n_tasks >= 36:
            if large_anneal_refine:
                anneal_deadline = min(st + 8.55, time.time() + 2.8)
                anneal_iters = 250000
                anneal_seeds = (7, 3, 29, 97)
            else:
                anneal_deadline = time.time()
                anneal_iters = 0
                anneal_seeds = ()
        else:
            anneal_deadline = min(st + 9.35, time.time() + 4.25)
            anneal_iters = 600000
            anneal_seeds = (1237, 809, 521) if score_std > 20.5 else (1237, 809, 7, 521)
        anneal_base_state = best[1]
        for anneal_seed in anneal_seeds:
            if anneal_deadline <= time.time() + 0.05:
                break
            improved_state = _anneal_single_task_reassign(p, anneal_base_state, anneal_deadline, anneal_seed, anneal_iters)
            improved_value = _state_model_value(p, improved_state, tm)
            if improved_value < best[0]:
                best[0] = improved_value
                best[1] = improved_state
                anneal_base_state = improved_state
    if tm == 'prop' and very_low_willingness and (p.n_tasks >= 25) and (p.n_tasks <= 32) and (len(p.all_couriers) >= p.n_tasks) and (time.time() < deadline):
        improved_state = _anneal_single_task_reassign(p, best[1], min(deadline, time.time() + 0.75), 1, 450000)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
    if tail_repartition and (not deep_tail_repartition) and (time.time() < deadline):
        improved_state = _local_repartition_three_expected(p, best[1], deadline, tm)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
            if time.time() < deadline:
                improved_state = _local_improve_expected(p, best[1], deadline, tm)
                improved_value = _state_model_value(p, improved_state, tm)
                if improved_value < best[0]:
                    best[0] = improved_value
                    best[1] = improved_state
    if deep_tail_repartition and time.time() < deadline:
        for _ in range(3):
            before_value = best[0]
            improved_state = _local_repartition_three_expected(p, best[1], deadline, tm)
            improved_value = _state_model_value(p, improved_state, tm)
            if improved_value < best[0]:
                best[0] = improved_value
                best[1] = improved_state
            if tb > 1.0 and time.time() < deadline:
                four_deadline = min(deadline, time.time() + 0.65)
                improved_state = _local_repartition_four_expected(p, best[1], four_deadline, tm)
                improved_value = _state_model_value(p, improved_state, tm)
                if improved_value < best[0]:
                    best[0] = improved_value
                    best[1] = improved_state
            if time.time() < deadline:
                improved_state = _local_improve_expected(p, best[1], deadline, tm)
                improved_value = _state_model_value(p, improved_state, tm)
                if improved_value < best[0]:
                    best[0] = improved_value
                    best[1] = improved_state
            if best[0] >= before_value - 1e-09 or time.time() >= deadline:
                break
    if tm == 'prop' and p.n_tasks <= 20 and (len(p.all_couriers) >= p.n_tasks) and (time.time() < deadline):
        improved_state = _local_pair_subset_reassign_expected(p, best[1], min(deadline, time.time() + 1.35), tm)
        improved_value = _state_model_value(p, improved_state, tm)
        if improved_value < best[0]:
            best[0] = improved_value
            best[1] = improved_state
        if p.n_tasks >= 9 and p.n_tasks <= 18 and (time.time() < deadline):
            triple_deadline = min(deadline - 1.65, time.time() + 4.6)
            if triple_deadline > time.time():
                improved_state = _local_triple_subset_reassign_expected(p, best[1], triple_deadline, tm)
                improved_value = _state_model_value(p, improved_state, tm)
                if improved_value < best[0]:
                    best[0] = improved_value
                    best[1] = improved_state
        if time.time() < deadline:
            improved_state = _local_pair_subset_reassign_expected(p, best[1], deadline, tm)
            improved_value = _state_model_value(p, improved_state, tm)
            if improved_value < best[0]:
                best[0] = improved_value
                best[1] = improved_state
    output = _state_to_output(best[1])
    FAIL_PENALTY = original_fail_penalty
    return output
