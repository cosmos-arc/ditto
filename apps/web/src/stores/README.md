# stores/ 目录

> Zustand 状态管理

## 目录说明

本目录使用 Zustand 进行全局状态管理，管理应用的客户端状态。

## 为什么选择 Zustand？

| 特性 | Zustand | Redux | Context API |
|------|---------|-------|-------------|
| 学习曲线 | ⭐⭐⭐⭐⭐ 简单 | ⭐⭐ 复杂 | ⭐⭐⭐⭐⭐ 简单 |
| 包体积 | < 1KB | ~3KB | 内置 |
| TypeScript 支持 | ⭐⭐⭐⭐⭐ 优秀 | ⭐⭐⭐⭐ 好 | ⭐⭐⭐⭐ 好 |
| 性能 | ⭐⭐⭐⭐⭐ 优秀 | ⭐⭐⭐⭐ 好 | ⭐⭐⭐ 一般 |
| DevTools | ⭐⭐⭐⭐ 支持 | ⭐⭐⭐⭐⭐ 内置 | ⭐⭐ 需要额外配置 |
| 中间件 | ⭐⭐⭐⭐⭐ 丰富 | ⭐⭐⭐⭐ 好 | ⭐⭐ 有限 |

**推荐理由**:
- API 简洁直观
- 无需 Provider 包裹
- 自动优化渲染（selector 机制）
- 支持 TypeScript
- 丰富的中间件（persist、devtools 等）

## 状态分层

```
┌─────────────────────────────────────────────────────────────┐
│                     应用状态全景                             │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │  Server State   │  │  Client State   │                   │
│  │  (TanStack Q)   │  │   (Zustand)     │                   │
│  ├─────────────────┤  ├─────────────────┤                   │
│  │ - 组合数据      │  │ - UI 状态       │                   │
│  │ - 回测结果      │  │ - 表单状态      │                   │
│  │ - 市场数据      │  │ - 过滤器状态    │                   │
│  │ - 风险事件      │  │ - 模态框状态    │                   │
│  └─────────────────┘  │ - 用户偏好      │                   │
│                       │ - 临时选择      │                   │
│                       └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

**状态分类**:
- **Server State**: 来自 API 的数据，使用 TanStack Query 管理
- **Client State**: 纯前端状态，使用 Zustand 管理

## 目录结构

```
stores/
├── useAuthStore.ts         # 认证状态
├── usePortfolioStore.ts    # 组合状态
├── useBacktestStore.ts     # 回测状态
├── useRiskStore.ts         # 风控状态
├── useResearchStore.ts     # 研究状态
├── useUIStore.ts           # UI 状态（侧边栏、主题等）
└── index.ts                # 导出所有 stores
```

## Store 设计模式

### 基础模式

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface MyStore {
  // 状态
  state: string;
  // 操作
  setState: (state: string) => void;
  // 重置
  reset: () => void;
}

export const useMyStore = create<MyStore>()(
  persist(
    (set) => ({
      state: 'initial',
      setState: (state) => set({ state }),
      reset: () => set({ state: 'initial' }),
    }),
    {
      name: 'my-store', // localStorage key
    }
  )
);
```

### 完整模板

```typescript
import { create } from 'zustand';
import { persist, devtools } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

// 1. 定义状态接口
interface ExampleStore {
  // 状态
  items: Item[];
  filter: Filter;
  ui: {
    isLoading: boolean;
    error: string | null;
    selectedId: string | null;
  };

  // 操作（同步）
  setItems: (items: Item[]) => void;
  setFilter: (filter: Filter) => void;
  selectItem: (id: string) => void;
  clearSelection: () => void;

  // 操作（异步）
  fetchItems: () => Promise<void>;
  addItem: (item: Item) => Promise<void>;

  // 重置
  reset: () => void;
}

// 2. 定义初始状态
const initialState = {
  items: [],
  filter: { status: 'all', search: '' },
  ui: {
    isLoading: false,
    error: null,
    selectedId: null,
  },
};

// 3. 创建 store
export const useExampleStore = create<ExampleStore>()(
  devtools(
    persist(
      immer((set, get) => ({
        ...initialState,

        // 同步操作
        setItems: (items) =>
          set((state) => {
            state.items = items;
          }),

        setFilter: (filter) =>
          set((state) => {
            state.filter = filter;
          }),

        selectItem: (id) =>
          set((state) => {
            state.ui.selectedId = id;
          }),

        clearSelection: () =>
          set((state) => {
            state.ui.selectedId = null;
          }),

        // 异步操作
        fetchItems: async () => {
          set((state) => {
            state.ui.isLoading = true;
            state.ui.error = null;
          });

          try {
            const items = await api.fetchItems();
            set((state) => {
              state.items = items;
            });
          } catch (error) {
            set((state) => {
              state.ui.error = error.message;
            });
          } finally {
            set((state) => {
              state.ui.isLoading = false;
            });
          }
        },

        addItem: async (item) => {
          const newItem = await api.addItem(item);
          set((state) => {
            state.items.push(newItem);
          });
        },

        // 重置
        reset: () => set(initialState),
      })),
      {
        name: 'example-store',
        // 持久化部分状态
        partialize: (state) => ({
          filter: state.filter,
        }),
      }
    ),
    { name: 'ExampleStore' }
  )
);
```

## 核心 Stores

### 1. useAuthStore - 认证状态

**状态**: ⏳ 待开发

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  id: string;
  username: string;
  role: 'admin' | 'trader' | 'viewer';
}

interface AuthStore {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;

  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  updateUser: (user: User) => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      login: async (username, password) => {
        const response = await fetch('/api/auth/login', {
          method: 'POST',
          body: JSON.stringify({ username, password }),
        });
        const { user, token } = await response.json();
        set({ user, token, isAuthenticated: true });
      },

      logout: () => {
        set({ user: null, token: null, isAuthenticated: false });
      },

      updateUser: (user) => {
        set({ user });
      },
    }),
    {
      name: 'auth-store',
    }
  )
);
```

### 2. usePortfolioStore - 组合状态

**状态**: ⏳ 待开发

```typescript
import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

interface Position {
  sid: string;
  symbol: string;
  shares: number;
  marketValue: number;
  weight: number;
}

interface PortfolioStore {
  // 状态
  currentPortfolio: {
    id: string;
    totalValue: number;
    cash: number;
    positions: Position[];
  } | null;
  rebalancePlan: RebalancePlan | null;
  selectedPositions: Set<string>;

  // UI 状态
  ui: {
    isLoading: boolean;
    selectedView: 'table' | 'chart';
    sortBy: string;
    sortOrder: 'asc' | 'desc';
  };

  // 操作
  setCurrentPortfolio: (portfolio: PortfolioStore['currentPortfolio']) => void;
  setRebalancePlan: (plan: RebalancePlan | null) => void;
  togglePositionSelection: (sid: string) => void;
  clearSelection: () => void;
  setView: (view: 'table' | 'chart') => void;
  setSorting: (sortBy: string, sortOrder: 'asc' | 'desc') => void;

  // 异步操作
  fetchPortfolio: () => Promise<void>;
  fetchRebalancePlan: (planId: string) => Promise<void>;
}
```

### 3. useBacktestStore - 回测状态

**状态**: ⏳ 待开发

```typescript
interface BacktestConfig {
  startDate: string;
  endDate: string;
  strategyId: string;
  initialCapital: number;
  rebalanceFreq: 'monthly' | 'weekly';
  maxPositions: number;
}

interface BacktestStore {
  // 配置
  config: BacktestConfig;

  // 结果
  result: BacktestResult | null;
  isRunning: boolean;
  progress: number;

  // UI 状态
  ui: {
    showConfig: boolean;
    selectedTab: 'overview' | 'trades' | 'metrics';
  };

  // 操作
  setConfig: (config: Partial<BacktestConfig>) => void;
  runBacktest: () => Promise<void>;
  cancelBacktest: () => void;
  setSelectedTab: (tab: string) => void;
}
```

### 4. useRiskStore - 风控状态

**状态**: ⏳ 待开发

```typescript
interface RiskStore {
  // 状态
  killSwitchLevel: 0 | 1 | 2 | 3;
  currentDrawdown: number;
  drawdownVelocity: number;
  riskEvents: RiskEvent[];

  // UI 状态
  ui: {
    showAlerts: boolean;
    autoRefresh: boolean;
  };

  // 操作
  updateRiskStatus: (status: RiskStatus) => void;
  acknowledgeEvent: (eventId: string) => void;
  toggleAlerts: () => void;
}
```

### 5. useUIStore - UI 状态

**状态**: ⏳ 待开发

```typescript
interface UIStore {
  // 侧边栏
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;

  // 主题
  theme: 'light' | 'dark' | 'system';
  setTheme: (theme: 'light' | 'dark' | 'system') => void;

  // 模态框
  modals: {
    backtestConfig: boolean;
    rebalanceDetail: boolean;
  };
  openModal: (name: string) => void;
  closeModal: (name: string) => void;

  // 通知
  notifications: Notification[];
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
}
```

## 最佳实践

### 1. 状态分离

**原则**: Server State 使用 TanStack Query，Client State 使用 Zustand

```typescript
// ❌ 不推荐：用 Zustand 管理 API 数据
const useData = create((set) => ({
  data: null,
  fetchData: async () => {
    const data = await fetch('/api/data').then(r => r.json());
    set({ data });
  },
}));

// ✅ 推荐：用 TanStack Query 管理 API 数据
function useData() {
  return useQuery({
    queryKey: ['data'],
    queryFn: () => fetch('/api/data').then(r => r.json()),
  });
}

// ✅ Zustand 只管理 UI 状态
const useUIStore = create((set) => ({
  selectedId: null,
  setSelectedId: (id) => set({ selectedId: id }),
}));
```

### 2. 选择器优化

**原则**: 使用选择器避免不必要的重渲染

```typescript
// ❌ 不推荐：整个对象变化导致重渲染
function Component() {
  const { items, filter } = useBacktestStore();
  return <div>{/* ... */}</div>;
}

// ✅ 推荐：只订阅需要的状态
function Component() {
  const items = useBacktestStore((state) => state.items);
  const filter = useBacktestStore((state) => state.filter);
  return <div>{/* ... */}</div>;
}

// ✅ 最佳：使用 shallow 比较多个字段
import { shallow } from 'zustand/shallow';

function Component() {
  const { items, filter } = useBacktestStore(
    (state) => ({ items: state.items, filter: state.filter }),
    shallow
  );
  return <div>{/* ... */}</div>;
}
```

### 3. 异步操作

**原则**: 异步操作应该结合 TanStack Query 的 mutations

```typescript
// ❌ 不推荐：在 Zustand 中管理异步状态
const useStore = create((set) => ({
  data: null,
  isLoading: false,
  error: null,
  fetchData: async () => {
    set({ isLoading: true });
    try {
      const data = await fetchData();
      set({ data, isLoading: false });
    } catch (error) {
      set({ error, isLoading: false });
    }
  },
}));

// ✅ 推荐：使用 TanStack Query mutations
function Component() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: fetchData,
    onSuccess: (data) => {
      queryClient.setQueryData(['data'], data);
    },
  });

  return <Button onClick={() => mutation.mutate()}>Fetch</Button>;
}
```

### 4. 持久化策略

**原则**: 只持久化必要的状态（用户偏好、配置）

```typescript
// ✅ 持久化部分状态
export const useStore = create(
  persist(
    (set) => ({
      // 持久化
      theme: 'light',
      sidebarCollapsed: false,

      // 不持久化
      isLoading: false,
      error: null,
    }),
    {
      name: 'app-store',
      partialize: (state) => ({
        // 只持久化这些字段
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
);
```

### 5. 中间件使用

**推荐中间件**:

```typescript
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import { immer } from 'zustand/middleware/immer';

export const useStore = create(
  devtools(
    persist(
      immer((set, get) => ({
        // store 实现
      })),
      {
        name: 'app-store',
      }
    ),
    {
      name: 'AppStore',
      enabled: process.env.NODE_ENV === 'development',
    }
  )
);
```

**中间件说明**:
- **devtools**: Redux DevTools 集成
- **persist**: localStorage 持久化
- **immer**: 不可变状态更新简化

## 与 TanStack Query 配合

### 状态分工

```
┌─────────────────────────────────────────────────────────────┐
│                    应用状态管理                              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  TanStack Query (Server State)          Zustand (Client)    │
│  ┌─────────────────────────────┐      ┌───────────────────┐ │
│  │ - 组合数据                  │      │ - UI 状态         │ │
│  │ - 回测结果                  │      │ - 表单状态        │ │
│  │ - 市场数据                  │      │ - 过滤器          │ │
│  │ - 风险事件                  │      │ - 用户偏好        │ │
│  └─────────────────────────────┘      └───────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 集成示例

```typescript
// 使用 TanStack Query 获取数据
function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => fetch('/api/portfolio').then(r => r.json()),
  });
}

// 使用 Zustand 管理 UI 状态
const useUIStore = create((set) => ({
  selectedView: 'table',
  setSelectedView: (view) => set({ selectedView: view }),
}));

// 在组件中组合使用
function PortfolioPage() {
  const { data, isLoading } = usePortfolio();
  const { selectedView, setSelectedView } = useUIStore();

  if (isLoading) return <Loading />;

  return (
    <div>
      <Tabs value={selectedView} onValueChange={setSelectedView}>
        <TabsList>
          <TabsTrigger value="table">表格视图</TabsTrigger>
          <TabsTrigger value="chart">图表视图</TabsTrigger>
        </TabsList>
      </Tabs>
      {selectedView === 'table' ? <Table data={data} /> : <Chart data={data} />}
    </div>
  );
}
```

## 测试

### 测试 Store

```typescript
import { renderHook, act } from '@testing-library/react';
import { useMyStore } from '@/stores/useMyStore';

describe('useMyStore', () => {
  it('should update state', () => {
    const { result } = renderHook(() => useMyStore());

    expect(result.current.state).toBe('initial');

    act(() => {
      result.current.setState('updated');
    });

    expect(result.current.state).toBe('updated');
  });

  it('should reset state', () => {
    const { result } = renderHook(() => useMyStore());

    act(() => {
      result.current.setState('updated');
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.state).toBe('initial');
  });
});
```

## 相关文档

- [Zustand 官方文档](https://zustand-demo.pmnd.rs/)
- [Zustand 中间件](https://github.com/pmndrs/zustand#middleware)
- [TanStack Query 文档](https://tanstack.com/query/latest)

---

**最后更新**: 2026-01-04
