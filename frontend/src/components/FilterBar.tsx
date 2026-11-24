import React from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

interface FilterBarProps {
  selectedCategory: string;
  onSelectCategory: (cat: string) => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  sortBy: string;
  onSortChange: (sort: string) => void;
  totalCount: number;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  selectedCategory,
  onSelectCategory,
  searchQuery,
  onSearchChange,
  sortBy,
  onSortChange,
  totalCount,
}) => {
  const categories = [
    { id: 'ALL', label: 'All Campus Outlets' },
    { id: 'MESS', label: 'Dining Halls (Messes)' },
    { id: 'CANTEEN', label: 'Canteens & Food Courts' },
  ];

  return (
    <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 py-4">
      {/* Category Glass Capsule Tabs */}
      <div className="flex items-center gap-1.5 p-1 rounded-2xl glass-panel border-white/10 overflow-x-auto scrollbar-none" role="tablist" aria-label="Outlet category filters">
        {categories.map((c) => {
          const isActive = selectedCategory === c.id;
          return (
            <button
              key={c.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => onSelectCategory(c.id)}
              className={`px-4 py-2 text-xs font-mono font-medium rounded-xl whitespace-nowrap transition-all duration-200 min-h-[44px] flex items-center justify-center ${
                isActive
                  ? 'bg-[#39FF14] text-[#070A08] font-bold shadow-[0_0_15px_rgba(57,255,20,0.4)]'
                  : 'text-[#8E9E93] hover:text-[#F4F7F5] hover:bg-white/[0.04]'
              }`}
            >
              {c.label}
            </button>
          );
        })}
      </div>

      {/* Search and Sort Island */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-[#5A695F] font-mono hidden lg:inline tracking-tight">
          {totalCount} {totalCount === 1 ? 'outlet indexed' : 'outlets indexed'}
        </span>

        {/* Smoked-Glass Search Input (16px on mobile prevents iOS Safari zoom) */}
        <div className="relative flex-1 sm:w-64">
          <Search className="w-4 h-4 text-[#8E9E93] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            aria-label="Search dining halls and cafes"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search dining halls & cafes..."
            className="w-full pl-10 pr-3.5 py-2.5 text-base sm:text-sm rounded-xl glass-panel text-[#F4F7F5] placeholder-[#5A695F] focus:outline-none focus:border-[#7DF9FF]/60 focus:shadow-[0_0_15px_rgba(125,249,255,0.2)] transition-all min-h-[44px]"
          />
        </div>

        {/* Sort Dropdown */}
        <div className="relative shrink-0 flex items-center gap-2 rounded-xl glass-panel px-3 py-2 border-white/10 min-h-[44px]">
          <SlidersHorizontal className="w-3.5 h-3.5 text-[#7DF9FF]" />
          <select
            value={sortBy}
            aria-label="Sort outlets by"
            onChange={(e) => onSortChange(e.target.value)}
            className="bg-transparent text-base sm:text-xs font-mono text-[#F4F7F5] focus:outline-none cursor-pointer pr-1 min-h-[36px]"
          >
            <option value="wait-asc" className="bg-[#0D140F] text-[#F4F7F5]">
              Shortest Wait
            </option>
            <option value="freshness" className="bg-[#0D140F] text-[#F4F7F5]">
              Most Recent
            </option>
            <option value="name-asc" className="bg-[#0D140F] text-[#F4F7F5]">
              Name (A-Z)
            </option>
            <option value="reports-desc" className="bg-[#0D140F] text-[#F4F7F5]">
              Most Reports
            </option>
          </select>
        </div>
      </div>
    </div>
  );
};
