# branch.py  (new)
# Branch target buffer with a one-bit predictor per entry.
#
#   - 8 entries (configurable), indexed by the least significant 3 bits of the
#     word address of the PC (instruction index & 7)
#   - each entry: valid, tag (full word address of the branch), target, 1-bit
#     prediction (1 = taken)
#   - prediction is made at ISSUE: if the entry is valid, the tag matches and
#     the bit is 1 the branch is predicted taken to the stored target;
#     otherwise it is predicted not taken (fall through to PC + 4)
#   - the entry is written when the branch resolves at the end of EX: the bit
#     becomes the actual outcome and the target is stored.  A different branch
#     that maps to the same entry replaces it (aliasing).


class BTB:
    def __init__(self, entries=8):
        self.entries = entries
        self.valid = [False] * entries
        self.tag = [0] * entries
        self.target = [0] * entries
        self.bit = [0] * entries

    def index(self, pc_word):
        return pc_word % self.entries         # = least significant 3 bits for 8 entries

    def predict(self, pc_word):
        """Returns (predicted_taken, predicted_target_word_address)."""
        i = self.index(pc_word)
        if self.valid[i] and self.tag[i] == pc_word and self.bit[i] == 1:
            return True, self.target[i]
        return False, pc_word + 1

    def update(self, pc_word, taken, target_word):
        i = self.index(pc_word)
        self.valid[i] = True
        self.tag[i] = pc_word
        self.target[i] = target_word
        self.bit[i] = 1 if taken else 0

    def dump(self):
        rows = []
        for i in range(self.entries):
            if self.valid[i]:
                rows.append('  [%d] branch @%d -> %d, predict %s'
                            % (i, self.tag[i] * 4, self.target[i] * 4,
                               'T' if self.bit[i] else 'NT'))
        return rows
