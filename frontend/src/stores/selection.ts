import { create } from 'zustand'

interface SelectionState {
  selectedNodeIds: Set<string>
  isAllSelected: boolean
  totalNodes: number

  // Actions
  toggleNode: (nodeId: string) => void
  selectNode: (nodeId: string) => void
  deselectNode: (nodeId: string) => void
  selectAll: (nodeIds: string[]) => void
  deselectAll: () => void
  setTotalNodes: (count: number) => void
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedNodeIds: new Set(),
  isAllSelected: false,
  totalNodes: 0,

  toggleNode: (nodeId) => {
    set((state) => {
      const newSet = new Set(state.selectedNodeIds)
      if (newSet.has(nodeId)) {
        newSet.delete(nodeId)
      } else {
        newSet.add(nodeId)
      }
      return {
        selectedNodeIds: newSet,
        isAllSelected: newSet.size === state.totalNodes && state.totalNodes > 0,
      }
    })
  },

  selectNode: (nodeId) => {
    set((state) => {
      const newSet = new Set(state.selectedNodeIds)
      newSet.add(nodeId)
      return {
        selectedNodeIds: newSet,
        isAllSelected: newSet.size === state.totalNodes && state.totalNodes > 0,
      }
    })
  },

  deselectNode: (nodeId) => {
    set((state) => {
      const newSet = new Set(state.selectedNodeIds)
      newSet.delete(nodeId)
      return {
        selectedNodeIds: newSet,
        isAllSelected: false,
      }
    })
  },

  selectAll: (nodeIds) => {
    set({
      selectedNodeIds: new Set(nodeIds),
      isAllSelected: true,
    })
  },

  deselectAll: () => {
    set({
      selectedNodeIds: new Set(),
      isAllSelected: false,
    })
  },

  setTotalNodes: (count) => {
    set({ totalNodes: count })
  },
}))
