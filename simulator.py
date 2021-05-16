from typing import *
import os
import math


class BuddySystem:
    def __init__(self, MAX_PAGENO):
        self.buddy_count = int(math.log2(MAX_PAGENO)) + 1
        self.buddy_lists = [[] for _ in range(self.buddy_count)]    # buddy_lists[i]: [start ids] of free page blocks of 2^i length
        self.pages = [-1 for _ in range(MAX_PAGENO)]                # An array, every entry a[i] represents the status of the i-th physical page. -1: free page, seqno(int >= 0): occupied by seqno.
        self.allocated_pages = {}                                   # Hashmap: seqno -> [allocated pages id]
        self.buddy_lists[-1].append(0)

    '''
    Request for #num of pages under #seqno
    Return the page ids of the allocation.
    '''
    def request_pages(self, seqno, num):
        # If space is enough for allocation
        idx = math.ceil(math.log2(num))
        allocated = False
        alloc_ids = []
        # Continuous allocation: Search upwards for free blocks
        for i in range(idx, self.buddy_count):
            if len(self.buddy_lists[i]) > 0:
                # Remove the first satifying block from buddy_list
                alloc_start_id = self.buddy_lists[i].pop(0)
                # Mark the corresponding pages with seqno
                for p in range(alloc_start_id, alloc_start_id+num):
                    self.pages[p] = seqno
                    alloc_ids.append(p)
                allocated = True
                break
        # Discontinuous allocation
        if not allocated:
            rest_length = num
            for i in range(len(self.pages)):
                if self.pages[i] == -1:
                    self.pages[i] = seqno
                    alloc_ids.append(i)
                    rest_length -= 1
                    if rest_length == 0:
                        allocated = True
                        break
        # Return the unused blocks back into buddy_lists.
        self.update_buddy_lists()
        return alloc_ids

    '''
    Allocate the pages, specified by page_ids, under seqno.
    If idx is not specified, then seqno is newly-allocated, need to update every entry.
    If idx is specified, then it is a faulted access, only need to update page_id of the idx-th entry.
    '''
    def allocate(self, page_ids, seqno, idx=None):
        if idx is None:
            self.allocated_pages[seqno] = page_ids
        else:
            self.allocated_pages[seqno][idx] = page_ids[-1]

    '''
    Free the num-th page of #seqno.
    Mark it as a freed page.
    '''
    def deallocate(self, seqno, num):
        # Mark the correponding page as free
        page_id = self.access(seqno, num)
        if page_id >= 0:
            self.pages[page_id] = -1
            self.allocated_pages[seqno][num] = -1
        # Merge the newly-freed page into buddy_lists, and update the buddy_lists
        self.update_buddy_lists()
        return page_id

    '''
    Access the num-th page of #seqno
    Return the page id of the access.
    Reurn -1 if the page is not found, e.g. has been deallocated / reclaimed.
    '''
    def access(self, seqno, num):
        alloc_ids = self.allocated_pages.get(seqno, None)
        if alloc_ids and len(alloc_ids) > num:
            return alloc_ids[num]
        else:
            return -1

    '''
    Given a page block, specified by start_page_id and length.
    Partition it into power-of-2 sub-blocks and return them to the buddy_lists.
    '''
    def partition_and_return(self, start_id, length):
        partitions = bin(length)[2:][::-1]
        for j in range(len(partitions)):
            if partitions[j] == '1':
                self.buddy_lists[j].append(start_id)
                start_id += 2**j
 
    '''
    update the buddy lists with the newly updated page status, i.e. self.pages.
    '''
    def update_buddy_lists(self):
        for i in range(self.buddy_count):
            self.buddy_lists[i] = []
        p1, p2 = 0, 0
        started = False
        for i in range(len(self.pages)):
            isFree = self.pages[i] < 0
            if isFree:
                p2 += 1
                started = True
            else:
                if started:
                    new_start_id = p1
                    new_length = p2 - p1
                    self.partition_and_return(new_start_id, new_length)
                    p2 += 1
                    p1 = p2
                else:
                    p1 += 1
                    p2 += 1
        if started:
            new_start_id = p1
            new_length = p2 - p1
            self.partition_and_return(new_start_id, new_length)

    '''
    Count how many free pages there are in the buddy_lists.
    Return the number of free pages.
    '''
    def count_free_pages(self):
        return sum([1 if s==-1 else 0 for s in self.pages])

                    


class LRU:
    def __init__(self, buddy_system, size_active, size_inactive):
        self.active_list = []                   # Active LRU: each entry is a tuple(page_id, seqno, num). Head is least recent.
        self.inactive_list = []                 # Inactive LRU: each entry is a tuple(page_id, seqno, num). Head is least recent.
        self.size_active = size_active
        self.size_inactive = size_inactive
        self.buddy_system = buddy_system

    '''
    When there is a page fault / demote, specified by (page_id, seqno, num), insert it into tail of inactive-LRU.
    If the size exceeds limit, reclaim from head of list.
    '''
    def insert_inactive(self, page_id, seqno, num):
        self.inactive_list.append((page_id, seqno, num))
        if len(self.inactive_list) > self.size_inactive:
            for _ in range(len(self.inactive_list) - self.size_inactive):
                (page_id, seqno, num) = self.inactive_list.pop(0)
                self.reclaim(page_id, seqno, num)
    
    '''
    When there is a new access to page_id, and it is in inactive-LRU, promote it to the tail of active-LRU.
    If the size exceeds limit, demote the head of list into inactive-LRU.
    '''
    def promote(self, page_id):
        list_id, idx = self.find_index(page_id)
        # Promote only if page_id is in inactive_list
        if list_id == 0:
            node = self.inactive_list.pop(idx)
            self.active_list.append(node)
            if len(self.active_list) > self.size_active:
                for _ in range(len(self.active_list) - self.size_active):
                    (page_id, seqno, num) = self.active_list.pop(0)
                    self.insert_inactive(page_id, seqno, num)
    
    '''
    Re-claim the page, specified by page_id, seqno, num.
    '''
    def reclaim(self, page_id, seqno, num):
        self.delete(page_id)
        self.buddy_system.deallocate(seqno, num)

    '''
    Re-claim the least-recently-used n pages from LRU.
    '''
    def reclaim_n_pages(self, n):
        for _ in range(n):
            if len(self.inactive_list) > 0:
                (page_id, seqno, num) = self.inactive_list.pop(0)
            elif len(self.active_list) > 0:
                (page_id, seqno, num) = self.active_list.pop(0)
            self.reclaim(page_id, seqno, num)

    '''
    Delete the node, specified by page_id, from LRU.
    '''
    def delete_old(self, page_id):
        list_id, idx = self.find_index(page_id)
        if list_id == 0:
            self.inactive_list.pop(idx)
        elif list_id == 1:
            self.active_list.pop(idx)

    def delete(self, page_id):
        for node in self.inactive_list:
            if node[0] == page_id:
                self.inactive_list.remove(node)
        for node in self.active_list:
            if node[0] == page_id:
                self.active_list.remove(node)

    '''
    Find the index of list, and index of node, specifed by page_id.
    Return list_id, idx. idx: index of node in list.
    list_id = 0 if node is in inactive-LRU, else 1.
    '''
    def find_index(self, page_id):
        for i in range(len(self.inactive_list)):
            if self.inactive_list[i][0] == page_id:
                return 0, i
        for i in range(len(self.active_list)):
            if self.active_list[i][0] == page_id:
                return 1, i
        return -1, -1



'''
Helper function: print the buddy lists.
'''
def print_buddy_lists(lists):
    print("\n- Buddy Lists:\n[")
    for i in range(len(lists)):
        ls = lists[i]
        print("\tlength = {}, start points: {}".format(2**i, ls))
    print("]")

'''
Helper function: print the page ids in the LRU list.
Least-recently-used pages are printed out first.
'''
def print_LRU(l, name):
    print("\n- {} (Least-recently-used page is at front):\n[".format(name), end='')
    for e in l:
        print(e[0], end=', ')
    print("]")



if __name__ == "__main__":
    # Read input file
    FILE_PATH = "./input.dat"
    with open(FILE_PATH, 'r') as file:
        lines = file.readlines()

    # Parse instrctions from input file
    instructions = []
    for line in lines:
        action, seqno, num = line.split("\t")[0], int(line.split("\t")[1]), int(line.split("\t")[2])
        instructions.append({'action': action, 'seqno': seqno, 'num': num})

    # Simulator specifications
    MAX_PAGENO = 512    # physical page numbers are between 0~511, in total 512 physical pages
    LEN_LIST = 250      # length of active and inactive list

    # Materialize the buddy system and reclamation system.
    buddy_system = BuddySystem(MAX_PAGENO)
    reclaim_system = LRU(buddy_system, LEN_LIST, LEN_LIST) 
    
    # Simulation starts here.
    line = 1
    for instr in instructions:
        action, seqno, num = instr['action'], instr['seqno'], instr['num']
        if action == 'A':
            n_pages = num - buddy_system.count_free_pages()
            if n_pages <= 0: 
                # There is enough free pages for allocation, directly do the allocation
                page_ids = buddy_system.request_pages(seqno, num)
            else:
                # There is no enough free pages, reclaim the LRU pages first and do allocation
                reclaim_system.reclaim_n_pages(n_pages)
                page_ids = buddy_system.request_pages(seqno, num)
            buddy_system.allocate(page_ids, seqno)
            for idx, p_id in enumerate(page_ids):
                # Insert allocated pages into reclamation inactive-LRU.
                reclaim_system.insert_inactive(p_id, seqno, idx)
        if action == 'X':
            page_id = buddy_system.access(seqno, num)
            if page_id >= 0:
                # If it is a valid page, promote it.
                reclaim_system.promote(page_id)
            else:
                # If the page is not found, need to do page fault again.
                n_pages = 1 - buddy_system.count_free_pages()
                if n_pages <= 0:
                    page_ids = buddy_system.request_pages(seqno, 1)
                else:
                    reclaim_system.reclaim_n_pages(n_pages)
                    page_ids = buddy_system.request_pages(seqno, 1)
                buddy_system.allocate(page_ids, seqno, idx=num)
                reclaim_system.insert_inactive(page_ids[-1], seqno, num)
        if action == 'F':
            page_id = buddy_system.deallocate(seqno, num)
            reclaim_system.delete(page_id)
        print("-line {}: {} {} {} -> completed.".format(line, action, seqno, num))
        line += 1
    
    print_buddy_lists(buddy_system.buddy_lists)
    print_LRU(reclaim_system.inactive_list, "Inactive-LRU")
    print("Length =", len(reclaim_system.inactive_list))
    print_LRU(reclaim_system.active_list, "Active-LRU")
    print("Length =", len(reclaim_system.active_list))
    


        