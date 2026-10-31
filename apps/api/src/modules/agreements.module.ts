import { Module } from "@nestjs/common";
import { AgreementsController } from "../agreements.controller";

@Module({ controllers: [AgreementsController] })
export class AgreementsModule {}
