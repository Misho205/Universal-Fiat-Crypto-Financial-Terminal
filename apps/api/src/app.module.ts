import { Module } from "@nestjs/common";
import { OrdersModule } from "./modules/orders.module";
import { AgreementsModule } from "./modules/agreements.module";
import { MethodsQuotesModule } from "./modules/methods-quotes.module";
import { InstructionsModule } from "./modules/instructions.module";
import { MiscModule } from "./modules/misc.module";

@Module({
  imports: [OrdersModule, AgreementsModule, MethodsQuotesModule, InstructionsModule, MiscModule],
})
export class AppModule {}
