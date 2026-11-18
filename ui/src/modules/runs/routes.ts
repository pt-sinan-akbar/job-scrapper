import type { RouteRecordRaw } from 'vue-router'
import { httpClient } from '@/core/http/httpClient'
import { RunRemoteDataSource } from '@/modules/runs/data/datasources/RunRemoteDataSource'
import { RunRepositoryImpl } from '@/modules/runs/data/repositories/RunRepositoryImpl'
import { GetRunOptionsUseCase } from '@/modules/runs/domain/usecases/GetRunOptionsUseCase'
import { GetRunUseCase } from '@/modules/runs/domain/usecases/GetRunUseCase'
import { StartRunUseCase } from '@/modules/runs/domain/usecases/StartRunUseCase'
import { provideRunUseCases } from '@/modules/runs/presentation/stores/runUseCases'

const repository = new RunRepositoryImpl(new RunRemoteDataSource(httpClient))

provideRunUseCases({
  getOptions: new GetRunOptionsUseCase(repository),
  getRun: new GetRunUseCase(repository),
  startRun: new StartRunUseCase(repository),
})

export const runRoutes: RouteRecordRaw[] = [
  {
    path: '/runs',
    name: 'runs',
    meta: { title: 'Runs' },
    component: () => import('@/modules/runs/presentation/pages/RunsPage.vue'),
  },
]
