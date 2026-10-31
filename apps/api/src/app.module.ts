import { Module } from "@nestjs/common";
import { OrdersController } from "./orders.controller";
import { AgreementsController } from "./agreements.controller";
import { MethodsQuotesController } from "./methods.controller";
import { InstructionsController } from "./instructions.controller";
import { MiscController } from "./misc.controller";
import { DevicesController } from "./orders.controller";

@Module({
  controllers: [OrdersController, AgreementsController, MethodsQuotesController, InstructionsController, DevicesController, MiscController],
})
export class AppModule {}
