import type { RouteRecordRaw } from 'vue-router'
import { httpClient } from '@/core/http/httpClient'
import { ScrapeRemoteDataSource } from '@/modules/scrapes/data/datasources/ScrapeRemoteDataSource'
import { ScrapeRepositoryImpl } from '@/modules/scrapes/data/repositories/ScrapeRepositoryImpl'
import { GetLatestScrapeUseCase } from '@/modules/scrapes/domain/usecases/GetLatestScrapeUseCase'
import { GetScrapeOptionsUseCase } from '@/modules/scrapes/domain/usecases/GetScrapeOptionsUseCase'
import { GetScrapeUseCase } from '@/modules/scrapes/domain/usecases/GetScrapeUseCase'
import { SendLatestScrapeToDiscordUseCase } from '@/modules/scrapes/domain/usecases/SendLatestScrapeToDiscordUseCase'
import { StartScrapeUseCase } from '@/modules/scrapes/domain/usecases/StartScrapeUseCase'
import { provideScrapeUseCases } from '@/modules/scrapes/presentation/stores/scrapeUseCases'

const repository = new ScrapeRepositoryImpl(new ScrapeRemoteDataSource(httpClient))

provideScrapeUseCases({
  getOptions: new GetScrapeOptionsUseCase(repository),
  getScrape: new GetScrapeUseCase(repository),
  getLatestScrape: new GetLatestScrapeUseCase(repository),
  startScrape: new StartScrapeUseCase(repository),
  sendLatestScrapeToDiscord: new SendLatestScrapeToDiscordUseCase(repository),
})

export const scrapeRoutes: RouteRecordRaw[] = [
  {
    path: '/scrapes',
    name: 'scrapes',
    meta: { title: 'Runs' },
    component: () => import('@/modules/scrapes/presentation/pages/ScrapesPage.vue'),
  },
]
