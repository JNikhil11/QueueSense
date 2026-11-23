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
    { id: 'ALL', label: 'All Outlets' },
    { id: 'MESS', label: 'Messes (Dining Halls)' },
    { id: 'CANTEEN', label: 'Canteens & Bistros' },
  ];

  return (
    <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 py-4">
      {/* Category Pills */}
      <div className="flex items-center gap-1.5 p-1 bg-surface-card rounded-xl border border-surface-border overflow-x-auto">
        {categories.map((c) => (
          <button
            key={c.id}
            onClick={() => onSelectCategory(c.id)}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg whitespace-nowrap transition-all duration-150 ${
              selectedCategory === c.id
                ? 'bg-neon-green/20 text-neon-green border border-neon-green/40 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-surface-elevated'
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Search and Sort */}
      <div className="flex items-center gap-3">
        <span className="text-xs text-slate-500 font-mono hidden lg:inline">
          {totalCount} {totalCount === 1 ? 'outlet' : 'outlets'}
        </span>
        {/* Search */}
        <div className="relative flex-1 sm:w-64">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search campus outlets..."
            className="w-full pl-9 pr-3 py-1.5 text-xs sm:text-sm bg-surface-card border border-surface-border rounded-xl text-slate-100 placeholder-slate-500 focus:outline-none focus:border-neon-blue focus:ring-1 focus:ring-neon-blue transition-colors"
          />
        </div>

        {/* Sort */}
        <div className="relative shrink-0 flex items-center gap-1.5 bg-surface-card border border-surface-border rounded-xl px-2.5 py-1.5">
          <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={sortBy}
            onChange={(e) => onSortChange(e.target.value)}
            className="bg-transparent text-xs text-slate-300 font-medium focus:outline-none cursor-pointer"
          >
            <option value="wait-asc" className="bg-surface-card text-slate-200">
              Shortest Wait
            </option>
            <option value="freshness" className="bg-surface-card text-slate-200">
              Most Recent
            </option>
            <option value="name-asc" className="bg-surface-card text-slate-200">
              Name (A-Z)
            </option>
            <option value="reports-desc" className="bg-surface-card text-slate-200">
              Most Reports
            </option>
          </select>
        </div>
      </div>
    </div>
  );
};
